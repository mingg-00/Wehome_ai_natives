from __future__ import annotations

import json
from typing import Any, Protocol

import requests

from config.settings import settings


class DirectorProvider(Protocol):
    name: str

    def request_storyboard_text(self, prompt: str, input_data: dict[str, Any]) -> str:
        ...


class GeminiDirectorProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        api_url: str | None = None,
        timeout_seconds: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model_name = model_name if model_name is not None else settings.gemini_model
        self.api_url = api_url if api_url is not None else settings.gemini_api_url
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.request_timeout_seconds
        self.session = session or requests.Session()

    def request_storyboard_text(self, prompt: str, input_data: dict[str, Any]) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        response = self.session.post(
            self.api_url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        response_json = response.json()
        try:
            return response_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("gemini API response is missing the expected text payload.") from exc


class AnthropicDirectorProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        api_url: str | None = None,
        timeout_seconds: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key
        self.model_name = model_name if model_name is not None else settings.anthropic_model
        self.api_url = api_url if api_url is not None else settings.anthropic_api_url
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.request_timeout_seconds
        self.session = session or requests.Session()

    def request_storyboard_text(self, prompt: str, input_data: dict[str, Any]) -> str:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")

        response = self.session.post(
            self.api_url,
            headers={
                "Content-Type": "application/json",
                "anthropic-version": settings.anthropic_version,
                "x-api-key": self.api_key,
            },
            json={
                "model": self.model_name,
                "max_tokens": settings.anthropic_max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        response_json = response.json()
        try:
            for content_block in response_json["content"]:
                if content_block.get("type") == "text":
                    return content_block["text"].strip()
        except (KeyError, TypeError) as exc:
            raise RuntimeError("anthropic API response is missing the expected text payload.") from exc
        raise RuntimeError("anthropic API response did not include a text content block.")


class LocalTemplateDirectorProvider:
    name = "local_template"

    def request_storyboard_text(self, prompt: str, input_data: dict[str, Any]) -> str:
        brand_name = str(input_data.get("brand_name") or "Company")
        image_urls = list(input_data.get("image_urls") or [])
        fallback_asset = image_urls[0] if image_urls else ""
        summary_points = [str(point) for point in input_data.get("summary_points", []) if str(point).strip()]
        hook = summary_points[0] if summary_points else f"{brand_name}의 브랜드 가치를 소개합니다."
        strength = summary_points[1] if len(summary_points) > 1 else hook

        storyboard = {
            "video_metadata": {
                "concept": f"{brand_name} 브랜드 소개",
                "bgm_mood": "modern clean corporate",
                "target_audience": "potential customers and partners",
            },
            "scenes": [
                {
                    "scene_number": 1,
                    "duration": "0~3s",
                    "section": "HOOK",
                    "matched_asset": image_urls[0] if len(image_urls) > 0 else fallback_asset,
                    "camera_effect": "Zoom-in",
                    "caption": f"{brand_name}, 한눈에 보는 브랜드",
                    "tts_script": hook[:120],
                },
                {
                    "scene_number": 2,
                    "duration": "3~7s",
                    "section": "VALUE",
                    "matched_asset": image_urls[1] if len(image_urls) > 1 else fallback_asset,
                    "camera_effect": "Slow pan",
                    "caption": "신뢰할 수 있는 핵심 가치",
                    "tts_script": strength[:120],
                },
                {
                    "scene_number": 3,
                    "duration": "7~10s",
                    "section": "CTA",
                    "matched_asset": image_urls[2] if len(image_urls) > 2 else fallback_asset,
                    "camera_effect": "Fade-in",
                    "caption": f"{brand_name}와 함께 시작하세요",
                    "tts_script": f"{brand_name}의 더 많은 이야기를 지금 확인해보세요.",
                },
            ],
            "recommended_hashtags": ["#Brand", "#CorporateVideo", "#Promotion"],
        }
        return json.dumps(storyboard, ensure_ascii=False)


def create_director_provider(
    provider_name: str,
    api_key: str | None = None,
    model_name: str | None = None,
    api_url: str | None = None,
    timeout_seconds: int | None = None,
    session: requests.Session | None = None,
) -> DirectorProvider:
    normalized_provider = provider_name.lower()
    if normalized_provider == "gemini":
        return GeminiDirectorProvider(api_key, model_name, api_url, timeout_seconds, session)
    if normalized_provider == "anthropic":
        return AnthropicDirectorProvider(api_key, model_name, api_url, timeout_seconds, session)
    if normalized_provider in {"local", "local_template", "template"}:
        return LocalTemplateDirectorProvider()
    raise RuntimeError(f"Unsupported director provider: {provider_name}")
