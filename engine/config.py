"""환경설정. .env가 있으면 로드하고, 없으면 합리적 기본값을 사용한다.

위홈 CS 챗봇과 동일한 컨벤션(OPENAI_API_KEY, llm_enabled)을 유지한다.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv 미설치 시에도 동작
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"        # 생성된 콘텐츠(초안/승인본) 저장 위치
DATA_DIR = BASE_DIR / "data"            # 토픽 백로그 등


class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    # 실제 위홈 예약 API (값이 있으면 샘플 대신 실제 API 호출)
    wehome_api_base: str = os.getenv("WEHOME_API_BASE", "").strip()
    wehome_api_key: str = os.getenv("WEHOME_API_KEY", "").strip()

    # Reddit 공식 API (읽기 전용 검색용) — reddit.com/prefs/apps 에서 발급
    reddit_client_id: str = os.getenv("REDDIT_CLIENT_ID", "").strip()
    reddit_client_secret: str = os.getenv("REDDIT_CLIENT_SECRET", "").strip()

    # SNS 자사 계정 게시용 토큰 (없으면 dry-run 미리보기로 동작)
    # X(Twitter): OAuth 1.0a 정적 토큰(권장·만료없음) — 4개 모두 있으면 우선 사용
    x_api_key: str = os.getenv("X_API_KEY", "").strip()
    x_api_secret: str = os.getenv("X_API_SECRET", "").strip()
    x_access_token: str = os.getenv("X_ACCESS_TOKEN", "").strip()
    x_access_secret: str = os.getenv("X_ACCESS_SECRET", "").strip()
    x_bearer_token: str = os.getenv("X_BEARER_TOKEN", "").strip()        # (대안) OAuth2 user token
    meta_access_token: str = os.getenv("META_ACCESS_TOKEN", "").strip()        # Facebook/IG 용 User 토큰
    threads_access_token: str = os.getenv("META_ACCESS_TOKEN_THREADS", "").strip()  # Threads 전용 토큰
    fb_page_token: str = os.getenv("FB_PAGE_TOKEN", "").strip()          # Facebook 페이지 전용 토큰 (게시용)
    fb_app_id: str = os.getenv("FB_APP_ID", "").strip()                   # Meta 앱 ID (장기 토큰 교환용)
    fb_app_secret: str = os.getenv("FB_APP_SECRET", "").strip()           # Meta 앱 시크릿 (장기 토큰 교환용)
    ig_user_id: str = os.getenv("IG_USER_ID", "").strip()
    fb_page_id: str = os.getenv("FB_PAGE_ID", "").strip()
    threads_user_id: str = os.getenv("THREADS_USER_ID", "").strip()
    youtube_client_id: str = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    youtube_client_secret: str = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    youtube_access_token: str = os.getenv("YOUTUBE_ACCESS_TOKEN", "").strip()
    youtube_refresh_token: str = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
    pinterest_token: str = os.getenv("PINTEREST_TOKEN", "").strip()
    pinterest_board_id: str = os.getenv("PINTEREST_BOARD_ID", "").strip()

    @property
    def llm_enabled(self) -> bool:
        """키가 있으면 실제 LLM 생성, 없으면 오프라인 스켈레톤 모드."""
        return bool(self.openai_api_key)

    @property
    def wehome_api_enabled(self) -> bool:
        """실제 위홈 API 연동 여부 (미설정 시 샘플 데이터 사용)."""
        return bool(self.wehome_api_base)

    @property
    def reddit_enabled(self) -> bool:
        """Reddit 공식 API 사용 가능 여부 (미설정 시 비인증 폴백 시도)."""
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @property
    def x_oauth1_enabled(self) -> bool:
        """X OAuth 1.0a 정적 토큰 4종이 모두 있으면 True(만료 없는 안정 게시)."""
        return bool(self.x_api_key and self.x_api_secret
                    and self.x_access_token and self.x_access_secret)


settings = Settings()
