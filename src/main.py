import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from analyzer import classify_grade, classify_performance_label
    from discord_notifier import build_report_message, send_discord_webhook
    from insight_generator import generate_insights
    from kpi_summary import generate_kpi_summary
    from ingest import extract_video_id_from_url, infer_platform_from_url, prepare_records
    from instagram_client import (
        InstagramAPIError,
        InstagramConfig,
        fetch_instagram_metrics_for_account,
        fetch_instagram_metrics_from_url,
    )
    from youtube_client import (
        YouTubeAPIError,
        YouTubeConfig,
        fetch_youtube_metrics_for_account,
        fetch_youtube_metrics_from_url,
    )
    from feedback_generator import generate_feedback
    from scorer import score_video
except ImportError:  # pragma: no cover - keeps script and package execution both working
    from src.analyzer import classify_grade, classify_performance_label
    from src.discord_notifier import build_report_message, send_discord_webhook
    from src.insight_generator import generate_insights
    from src.kpi_summary import generate_kpi_summary
    from src.ingest import extract_video_id_from_url, infer_platform_from_url, prepare_records
    from src.instagram_client import (
        InstagramAPIError,
        InstagramConfig,
        fetch_instagram_metrics_for_account,
        fetch_instagram_metrics_from_url,
    )
    from src.youtube_client import (
        YouTubeAPIError,
        YouTubeConfig,
        fetch_youtube_metrics_for_account,
        fetch_youtube_metrics_from_url,
    )
    from src.feedback_generator import generate_feedback
    from src.scorer import score_video


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "sample_metrics.json"
OUTPUT_DIR = PROJECT_ROOT / "output"
ANALYTICS_REPORT_PATH = OUTPUT_DIR / "analytics_report.json"
FEEDBACK_PATH = OUTPUT_DIR / "feedback_to_video_agent.json"
KPI_SUMMARY_PATH = OUTPUT_DIR / "kpi_summary.json"
LOG_PATH = OUTPUT_DIR / "analytics_agent.log"

logger = logging.getLogger("wehome.analytics_agent")


def load_dotenv_file(path: Path | None = None) -> None:
    dotenv_path = path or (PROJECT_ROOT / ".env")
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        if not name:
            continue

        value = value.strip().strip('"').strip("'")
        os.environ[name] = value


def load_metrics(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("sample_metrics.json must contain a JSON array.")

    return data


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    ensure_output_dir()

    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)


def build_report(records: List[Dict[str, Any]], source_dataset: str = "input records") -> Dict[str, Any]:
    report_rows: List[Dict[str, Any]] = []
    feedback_rows: List[Dict[str, Any]] = []

    for record in records:
        scores = score_video(record)
        grade = classify_grade(scores["cps"])
        performance_label = classify_performance_label(scores["cps"])
        insights = generate_insights(
            record,
            scores,
            grade=grade,
            performance_label=performance_label,
        )

        report_rows.append(
            {
                **record,
                **scores,
                "metrics": {
                    "completion_rate": scores["completion_rate"],
                    "engagement_rate": scores["engagement_rate"],
                    "share_rate": scores["share_rate"],
                },
                "grade": grade,
                "performance_label": performance_label,
                "strengths": insights["strengths"],
                "weaknesses": insights["weaknesses"],
                "recommended_actions": insights["recommended_actions"],
            }
        )

        feedback_rows.append(
            generate_feedback(
                record,
                scores["cps"],
                grade,
                performance_label,
                scores,
            )
        )

    kpi_summary = generate_kpi_summary(report_rows)
    report = {
        "report_type": "analytics_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": source_dataset,
        "summary": kpi_summary,
        "results": report_rows,
    }

    return {"report": report, "feedback": feedback_rows, "kpi_summary": kpi_summary}


def save_json(path: Path, payload: Dict[str, Any] | List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wehome SNS Analytics & Feedback Agent")
    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_PATH,
        help="Path to the input metrics JSON file.",
    )
    parser.add_argument(
        "--inspect-url",
        type=str,
        default="",
        help="Inspect a single SNS video URL and print inferred platform/video ID.",
    )
    parser.add_argument(
        "--instagram-url",
        action="append",
        default=[],
        help="Fetch metrics for one Instagram Reel/Video URL using the official Graph API. Can be repeated.",
    )
    parser.add_argument(
        "--instagram-all",
        action="store_true",
        help="Fetch and evaluate all Instagram media for the configured account.",
    )
    parser.add_argument(
        "--youtube-url",
        action="append",
        default=[],
        help="Fetch metrics for one YouTube video URL using Google OAuth credentials. Can be repeated.",
    )
    parser.add_argument(
        "--youtube-all",
        action="store_true",
        help="Fetch and evaluate recent videos for the configured YouTube account.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail immediately when input records are missing required fields.",
    )
    parser.add_argument(
        "--discord-webhook-url",
        type=str,
        default=os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        help="Optional Discord webhook URL for sending the generated report summary.",
    )
    parser.add_argument(
        "--discord-thread-name",
        type=str,
        default=os.getenv("DISCORD_THREAD_NAME", "").strip(),
        help="Optional Discord thread name for forum/media channels.",
    )
    return parser.parse_args()


def inspect_url(url: str) -> int:
    if not url:
        logger.error("No URL provided for inspection.")
        return 1

    platform = infer_platform_from_url(url)
    video_id = extract_video_id_from_url(url)
    logger.info("Detected platform: %s", platform)
    logger.info("Detected video ID: %s", video_id or "(not found)")
    logger.info("Source URL: %s", url)
    logger.info(
        "Direct metric extraction from a URL still requires official API credentials for the platform."
    )
    return 0


def build_instagram_config() -> InstagramConfig:
    access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
    ig_user_id = os.getenv("META_INSTAGRAM_ACCOUNT_ID", "").strip()
    graph_api_version = os.getenv("META_GRAPH_API_VERSION", "v21.0").strip() or "v21.0"

    if not access_token:
        raise ValueError("META_ACCESS_TOKEN is required for Instagram API access.")
    if not ig_user_id:
        raise ValueError("META_INSTAGRAM_ACCOUNT_ID is required for Instagram API access.")

    return InstagramConfig(
        access_token=access_token,
        ig_user_id=ig_user_id,
        graph_api_version=graph_api_version,
    )


def build_youtube_config() -> YouTubeConfig:
    access_token = os.getenv("YOUTUBE_ACCESS_TOKEN", "").strip()
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()

    if not access_token and not (client_id and client_secret and refresh_token):
        raise ValueError(
            "YouTube credentials are required. Set YOUTUBE_ACCESS_TOKEN or GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
        )

    return YouTubeConfig(
        access_token=access_token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )


def main() -> None:
    load_dotenv_file()
    args = parse_args()

    configure_logging()
    print("Analytics Agent MVP started.")

    if (args.instagram_all and args.instagram_url) or (args.youtube_all and args.youtube_url):
        logger.error("Use either account mode or URL mode for the same platform, not both.")
        raise SystemExit(1)

    if args.youtube_all:
        try:
            config = build_youtube_config()
            raw_records = fetch_youtube_metrics_for_account(config)
        except (ValueError, YouTubeAPIError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.youtube_url:
        try:
            config = build_youtube_config()
            raw_records = [fetch_youtube_metrics_from_url(url, config) for url in args.youtube_url]
        except (ValueError, YouTubeAPIError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.instagram_all:
        try:
            config = build_instagram_config()
            raw_records = fetch_instagram_metrics_for_account(config)
        except (ValueError, InstagramAPIError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.instagram_url:
        try:
            config = build_instagram_config()
            raw_records = [fetch_instagram_metrics_from_url(url, config) for url in args.instagram_url]
        except (ValueError, InstagramAPIError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.inspect_url:
        raise SystemExit(inspect_url(args.inspect_url))
    else:
        try:
            raw_records = load_metrics(args.input)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc

    try:
        records, warnings = prepare_records(raw_records, strict=args.strict)
    except ValueError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc

    for warning in warnings:
        logger.warning("%s", warning)

    print(f"Loaded {len(records)} video records.")

    bundle = build_report(records, source_dataset=str(args.input))
    report = bundle["report"]
    feedback = bundle["feedback"]
    kpi_summary = bundle["kpi_summary"]

    save_json(ANALYTICS_REPORT_PATH, report)
    save_json(FEEDBACK_PATH, feedback)
    save_json(KPI_SUMMARY_PATH, kpi_summary)

    summary = report["summary"]
    print(f"Total videos: {summary['total_videos']}")
    print(f"Average CPS: {summary['average_cps']}")
    print(f"Best video: {summary.get('best_video_name', summary['best_video'])} ({summary['best_cps']})")
    print(f"Worst video: {summary.get('worst_video_name', summary['worst_video'])} ({summary['worst_cps']})")
    print(f"A grade videos: {summary['grade_distribution']['A']}")
    print(f"B grade videos: {summary['grade_distribution']['B']}")
    print(f"C grade videos: {summary['grade_distribution']['C']}")
    print(f"D grade videos: {summary['grade_distribution']['D']}")
    if summary.get("platform_distribution"):
        print(f"Platform distribution: {summary['platform_distribution']}")
    print("Saved analytics report to output/analytics_report.json")
    print("Saved feedback to output/feedback_to_video_agent.json")
    print("Saved KPI summary to output/kpi_summary.json")

    if args.discord_webhook_url:
        try:
            message = build_report_message(report, feedback)
            send_discord_webhook(args.discord_webhook_url, message, thread_name=args.discord_thread_name)
            print("Sent analytics summary to Discord.")
        except RuntimeError as exc:
            logger.warning(
                "Discord summary send failed: %s. Check DISCORD_WEBHOOK_URL, webhook permissions, and whether the webhook still exists.",
                exc,
            )
    else:
        logger.warning(
            "Discord summary skipped because no webhook is configured. Set DISCORD_WEBHOOK_URL in .env or pass --discord-webhook-url."
        )

    print("Analytics Agent MVP completed.")


if __name__ == "__main__":
    main()
