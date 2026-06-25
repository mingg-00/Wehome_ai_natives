from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agents.analytics_agent import run_analytics_agent
from agents.sns_upload_agent import run_sns_agent
from agents.video_agent import run_video_agent
from config.settings import Settings, load_settings
from shared.json_utils import ensure_parent, read_json, utc_now_iso, write_json


ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class CampaignRequest:
    campaign_id: str
    requested_by: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CampaignRequest":
        data = data or {}
        return cls(
            campaign_id=str(data.get("campaign_id") or f"campaign-{int(time.time())}"),
            requested_by=data.get("requested_by"),
            notes=data.get("notes"),
        )


def _default_request() -> CampaignRequest:
    return CampaignRequest(campaign_id=f"campaign-{int(time.time())}")


def _result_path(settings: Settings, name: str) -> Path:
    return settings.data_dir / f"{name}_result.json"


def _write_stage_result(settings: Settings, name: str, result: dict[str, Any]) -> Path:
    path = _result_path(settings, name)
    write_json(path, result)
    return path


def _emit(progress: ProgressCallback | None, stage: str, state: str, message: str, **extra: Any) -> None:
    if progress is None:
        return
    progress(
        {
            "stage": stage,
            "state": state,
            "message": message,
            "timestamp": utc_now_iso(),
            **extra,
        }
    )


def run_campaign(
    request: dict[str, Any] | CampaignRequest | None = None,
    *,
    settings: Settings | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    if request is None:
        campaign_request = _default_request()
    elif isinstance(request, CampaignRequest):
        campaign_request = request
    else:
        campaign_request = CampaignRequest.from_dict(request)

    started_at = utc_now_iso()
    _emit(progress_callback, "campaign", "running", "Starting campaign", campaign_id=campaign_request.campaign_id)

    _emit(progress_callback, "video", "running", "Running video agent")
    video_result = run_video_agent(
        context={
            "campaign_id": campaign_request.campaign_id,
            "notes": campaign_request.notes,
            "contract_version": settings.contract_version,
        }
    )
    _write_stage_result(settings, "video", video_result)
    _emit(progress_callback, "video", "completed", "Video agent completed", result=video_result)

    _emit(progress_callback, "sns", "running", "Running SNS upload agent")
    sns_result = run_sns_agent(
        video_result,
        context={
            "campaign_id": campaign_request.campaign_id,
            "notes": campaign_request.notes,
            "contract_version": settings.contract_version,
        },
    )
    _write_stage_result(settings, "sns", sns_result)
    _emit(progress_callback, "sns", "completed", "SNS upload agent completed", result=sns_result)

    _emit(progress_callback, "analytics", "running", "Running analytics agent")
    analytics_result = run_analytics_agent(
        sns_result,
        context={
            "campaign_id": campaign_request.campaign_id,
            "notes": campaign_request.notes,
            "contract_version": settings.contract_version,
        },
    )
    _write_stage_result(settings, "analytics", analytics_result)
    _emit(progress_callback, "analytics", "completed", "Analytics agent completed", result=analytics_result)

    completed_at = utc_now_iso()
    summary = {
        "contract_version": settings.contract_version,
        "campaign_id": campaign_request.campaign_id,
        "requested_by": campaign_request.requested_by,
        "notes": campaign_request.notes,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "success"
        if all(stage.get("ok", True) for stage in (video_result, sns_result, analytics_result))
        else "partial_failure",
        "results": {
            "video": video_result,
            "sns": sns_result,
            "analytics": analytics_result,
        },
    }

    write_json(settings.data_dir / "summary.json", summary)
    _emit(progress_callback, "campaign", "completed", "Campaign completed", summary=summary)
    return summary


def _job_paths(settings: Settings) -> tuple[Path, Path, Path]:
    jobs_dir = settings.runtime_dir / "jobs"
    results_dir = settings.runtime_dir / "results"
    status_dir = settings.runtime_dir / "status"
    for path in (jobs_dir, results_dir, status_dir):
        path.mkdir(parents=True, exist_ok=True)
    return jobs_dir, results_dir, status_dir


def submit_job(
    request: dict[str, Any] | CampaignRequest,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or load_settings()
    jobs_dir, _, _ = _job_paths(settings)
    campaign_request = request if isinstance(request, CampaignRequest) else CampaignRequest.from_dict(request)

    job = {
        "job_id": campaign_request.campaign_id,
        "request": {
            "campaign_id": campaign_request.campaign_id,
            "requested_by": campaign_request.requested_by,
            "notes": campaign_request.notes,
        },
        "created_at": utc_now_iso(),
    }
    write_json(jobs_dir / f"{campaign_request.campaign_id}.json", job)
    return job


def worker_loop(*, settings: Settings | None = None, poll_interval: float | None = None) -> None:
    settings = settings or load_settings()
    jobs_dir, results_dir, status_dir = _job_paths(settings)
    interval = poll_interval or settings.job_poll_interval_seconds

    print(f"Orchestrator worker started. Watching {jobs_dir}")
    while True:
        job_files = sorted(jobs_dir.glob("*.json"))
        if not job_files:
            time.sleep(interval)
            continue

        for job_file in job_files:
            locked_file = job_file.with_suffix(".processing.json")
            try:
                job_file.replace(locked_file)
            except OSError:
                continue

            try:
                job_data = read_json(locked_file)
                request = CampaignRequest.from_dict(job_data.get("request"))
                status_path = status_dir / f"{request.campaign_id}.json"
                result_path = results_dir / f"{request.campaign_id}.json"

                def progress(event: dict[str, Any]) -> None:
                    write_json(status_path, event)
                    print(json.dumps(event, ensure_ascii=False))

                summary = run_campaign(request, settings=settings, progress_callback=progress)
                write_json(result_path, summary)
                write_json(settings.data_dir / "summary.json", summary)
                locked_file.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                error_payload = {
                    "job_id": job_file.stem,
                    "status": "failed",
                    "error": str(exc),
                    "timestamp": utc_now_iso(),
                }
                write_json(results_dir / f"{job_file.stem}.json", error_payload)
                write_json(settings.data_dir / "summary.json", error_payload)
                locked_file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Wehome campaign orchestrator")
    parser.add_argument("--worker", action="store_true", help="run as a background worker")
    parser.add_argument("--run-once", action="store_true", help="run a single campaign")
    parser.add_argument("--request", help="JSON payload for a single campaign run")
    args = parser.parse_args()

    settings = load_settings()
    ensure_parent(settings.data_dir / "summary.json")

    if args.worker:
        worker_loop(settings=settings)
        return 0

    if args.request:
        summary = run_campaign(json.loads(args.request), settings=settings)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.run_once:
        summary = run_campaign(settings=settings)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

