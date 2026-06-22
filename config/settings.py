from __future__ import annotations  # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화

import os                           # 환경변수와 파일 경로 처리를 위해 표준 라이브러리의 os 모듈을 사용
from dataclasses import dataclass   # 데이터 클래스 데코레이터를 가져와 설정 클래스를 정의

from dotenv import load_dotenv      # .env 파일에서 환경변수를 로드하기 위해 python-dotenv 라이브러리의 load_dotenv 함수를 사용


load_dotenv()


# 환경변수에서 정수 값을 읽어오는 함수
def _env_int(name: str, default: int) -> int:
    # 환경변수가 비어 있으면 기본값을 쓰고, 값이 있으면 정수로 변환한다.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


# 환경변수에서 부동소수점 값을 읽어오는 함수
def _env_float(name: str, default: float) -> float:
    # 재시도 간격처럼 소수점이 필요한 설정은 별도 파서로 처리한다.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


# 환경변수에서 불리언 값을 읽어오는 함수
def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


# 환경변수에서 쉼표로 구분된 목록을 읽어오는 함수
def _env_list(name: str, default: list[str]) -> list[str]:
    # 쉼표로 구분된 환경변수는 공백을 제거해 목록으로 변환한다.
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


# 디스코드 전송을 settings.py에서 직접 켜고 끄기 위한 단일 스위치
DISCORD_DELIVERY_ENABLED = False


# 설정 클래스는 .env에서 읽은 값과 기본값을 조합해 애플리케이션 전반에서 사용할 설정을 제공
@dataclass(frozen=True)
class AppSettings:
    # 핵심 비밀 값과 경로는 .env에서 읽고, 전송 토글은 이 파일의 상수로 직접 제어한다.
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    discord_webhook_url: str | None = os.getenv("DISCORD_WEBHOOK_URL")
    discord_delivery_enabled: bool = DISCORD_DELIVERY_ENABLED
    director_provider: str = os.getenv("DIRECTOR_PROVIDER", "gemini")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    anthropic_api_url: str = os.getenv("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
    anthropic_version: str = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
    anthropic_max_tokens: int = _env_int("ANTHROPIC_MAX_TOKENS", 4000)
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    video_provider: str = os.getenv("VIDEO_PROVIDER", "local")
    veo_api_key: str | None = os.getenv("VEO_API_KEY") or os.getenv("GEMINI_API_KEY")
    veo_model: str = os.getenv("VEO_MODEL", "veo-3.1-generate-preview")
    veo_aspect_ratio: str = os.getenv("VEO_ASPECT_RATIO", "9:16")
    veo_resolution: str = os.getenv("VEO_RESOLUTION", "720p")
    veo_duration_seconds: int = _env_int("VEO_DURATION_SECONDS", 8)
    veo_poll_interval_seconds: int = _env_int("VEO_POLL_INTERVAL_SECONDS", 10)
    veo_timeout_seconds: int = _env_int("VEO_TIMEOUT_SECONDS", 600)
    tts_provider: str = os.getenv("TTS_PROVIDER", "gtts")
    elevenlabs_api_key: str | None = os.getenv("ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
    elevenlabs_model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    elevenlabs_output_format: str = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    music_provider: str = os.getenv("MUSIC_PROVIDER", "local")
    music_api_key: str | None = os.getenv("MUSIC_API_KEY") or os.getenv("SUDO_API_KEY") or os.getenv("SUNO_API_KEY")
    music_api_url: str = os.getenv("MUSIC_API_URL") or os.getenv("SUDO_API_URL") or os.getenv("SUNO_API_URL", "")
    music_model: str = os.getenv("MUSIC_MODEL", "sudo")
    request_timeout_seconds: int = _env_int("REQUEST_TIMEOUT_SECONDS", 20)
    storyboard_retry_attempts: int = _env_int("STORYBOARD_RETRY_ATTEMPTS", 3)
    storyboard_retry_backoff_seconds: float = _env_float("STORYBOARD_RETRY_BACKOFF_SECONDS", 1.5)
    discord_retry_attempts: int = _env_int("DISCORD_RETRY_ATTEMPTS", 3)
    discord_retry_backoff_seconds: float = _env_float("DISCORD_RETRY_BACKOFF_SECONDS", 1.5)
    assets_dir: str = os.getenv("ASSETS_DIR", "assets")
    audio_dir: str = os.getenv("AUDIO_DIR", os.path.join("output", "temp_audio"))
    video_dir: str = os.getenv("VIDEO_DIR", os.path.join("output", "final_video"))
    bgm_dir: str = os.getenv("BGM_DIR", "bgm")
    bgm_volume: float = _env_float("BGM_VOLUME", 0.18)
    storyboard_cache_path: str = os.getenv("STORYBOARD_CACHE_PATH", os.path.join("output", "storyboard_cache.json"))
    storyboard_cache_enabled: bool = _env_bool("STORYBOARD_CACHE_ENABLED", True)
    storyboard_force_refresh: bool = _env_bool("STORYBOARD_FORCE_REFRESH", False)
    company_profile_output_path: str = os.getenv(
        "COMPANY_PROFILE_OUTPUT_PATH",
        os.path.join("output", "company_profiles", "company_profile.json"),
    )
    company_brand_name: str = os.getenv("COMPANY_BRAND_NAME", "")
    company_source_urls: tuple[str, ...] = tuple(_env_list("COMPANY_SOURCE_URLS", []))
    company_crawl_timeout_seconds: int = _env_int("COMPANY_CRAWL_TIMEOUT_SECONDS", 15)
    company_max_pages: int = _env_int("COMPANY_MAX_PAGES", 3)
    company_crawl_continue_on_error: bool = _env_bool("COMPANY_CRAWL_CONTINUE_ON_ERROR", True)
    company_body_max_chars: int = _env_int("COMPANY_BODY_MAX_CHARS", 1200)

    @property
    def gemini_api_url(self) -> str:
        # Gemini REST 엔드포인트는 모델명만 바뀌고 경로 구조는 동일하다.
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.gemini_model}:generateContent"
        )

    def gemini_headers(self) -> dict[str, str]:
        # API 키는 쿼리 파라미터가 아니라 헤더로만 전송해 로그 노출을 막는다.
        headers = {"Content-Type": "application/json"}
        if self.gemini_api_key:
            headers["x-goog-api-key"] = self.gemini_api_key
        return headers


# 전역 설정 인스턴스를 만들어 애플리케이션 전반에서 재사용
settings = AppSettings()


# 렌더링과 캐시 저장에 필요한 폴더를 실행 전에 미리 만듦
def ensure_directories(*paths: str) -> None:
    # 렌더링과 캐시 저장에 필요한 폴더를 실행 전에 미리 만든다.
    for path in paths:
        if path:
            os.makedirs(path, exist_ok=True)
