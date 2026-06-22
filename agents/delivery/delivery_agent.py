from __future__ import annotations

import os
import time
from typing import Optional

import requests

from config.settings import settings


class DeliveryError(RuntimeError):
    pass


class DeliveryAgent:
    def __init__(
        self,
        enabled: bool | None = None,
        webhook_url: str | None = None,
        session: Optional[requests.Session] = None,
        retry_attempts: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        self.enabled = enabled if enabled is not None else settings.discord_delivery_enabled
        self.webhook_url = webhook_url if webhook_url is not None else settings.discord_webhook_url
        self.session = session or requests.Session()
        self.retry_attempts = retry_attempts if retry_attempts is not None else settings.discord_retry_attempts
        self.retry_backoff_seconds = (
            retry_backoff_seconds if retry_backoff_seconds is not None else settings.discord_retry_backoff_seconds
        )

        if not self.enabled:
            # 전송 기능이 꺼져 있으면 웹훅이 없어도 객체는 생성 가능하게 둔다.
            return

        if not self.webhook_url:
            # 전송 단계는 웹훅이 없으면 동작할 수 없으므로 생성 시점에 바로 실패시킨다.
            raise DeliveryError("DISCORD_WEBHOOK_URL is not configured.")

    def send_video(self, output_video_path: str, caption_text: str) -> bool:
        # 기능 토글이 꺼져 있으면 실제 업로드를 건너뛴다.
        if not self.enabled:
            print("[DeliveryAgent] Discord delivery is disabled. Upload skipped.")
            return False

        # 디스코드로 보낼 파일이 없으면 바로 예외를 올려 잘못된 호출을 드러낸다.
        if not os.path.exists(output_video_path):
            raise FileNotFoundError(f"Video file not found: {output_video_path}")

        payload = {"content": f"[POST_REQUEST]\n{caption_text}"}
        last_error: Exception | None = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                # 파일은 매 시도마다 다시 열어야 재시도 시에도 안정적으로 전송된다.
                with open(output_video_path, "rb") as file_handle:
                    files = {"file": (os.path.basename(output_video_path), file_handle, "video/mp4")}
                    response = self.session.post(self.webhook_url, data=payload, files=files, timeout=30)

                if response.status_code in (200, 204):
                    print("[DeliveryAgent] Discord delivery succeeded.")
                    return True

                if response.status_code == 429 or 500 <= response.status_code < 600:
                    # 속도 제한이나 서버 오류는 일시적일 수 있어 재시도 대상으로 둔다.
                    last_error = DeliveryError(
                        f"Discord delivery failed with retryable status: {response.status_code} {response.reason}"
                    )
                else:
                    # 4xx 중 복구 불가한 오류는 즉시 실패시킨다.
                    raise DeliveryError(
                        f"Discord delivery failed: {response.status_code} {response.reason}"
                    )
            except requests.RequestException as exc:
                # 네트워크 문제도 재시도에 포함한다.
                last_error = DeliveryError(f"Discord delivery request failed: {exc.__class__.__name__}")

            if attempt < self.retry_attempts:
                # 점진적 backoff로 짧은 간격의 연속 실패를 피한다.
                time.sleep(self.retry_backoff_seconds * attempt)

        # 모든 재시도가 실패했을 때만 최종 오류를 올린다.
        raise DeliveryError(
            f"Discord delivery failed after {self.retry_attempts} attempts."
        ) from last_error
