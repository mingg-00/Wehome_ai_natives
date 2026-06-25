from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    instagram_access_token: str
    youtube_client_id: str
    youtube_client_secret: str
    contract_version: str
    orchestrator_mode: str
    data_dir: Path
    runtime_dir: Path
    job_poll_interval_seconds: float
    discord_guild_id: int | None


def _path(value: str | None, default: str) -> Path:
    return Path(value or default)


def load_settings() -> Settings:
    load_dotenv()
    guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
        instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip(),
        youtube_client_id=os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
        youtube_client_secret=os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
        contract_version=os.getenv("CONTRACT_VERSION", "1.0.0").strip(),
        orchestrator_mode=os.getenv("ORCHESTRATOR_MODE", "direct").strip().lower(),
        data_dir=_path(os.getenv("DATA_DIR"), "data"),
        runtime_dir=_path(os.getenv("RUNTIME_DIR"), "runtime"),
        job_poll_interval_seconds=float(os.getenv("JOB_POLL_INTERVAL_SECONDS", "2.0")),
        discord_guild_id=int(guild_id_raw) if guild_id_raw else None,
    )

