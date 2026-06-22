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
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

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
            raise RuntimeError("gemini API 응답에서 예상한 텍스트 payload를 찾을 수 없습니다.") from exc


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
            raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

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
            raise RuntimeError("anthropic API 응답에서 예상한 텍스트 payload를 찾을 수 없습니다.") from exc
        raise RuntimeError("anthropic API 응답에 텍스트 콘텐츠 블록이 없습니다.")


class LocalTemplateDirectorProvider:
    name = "local_template"

    def request_storyboard_text(self, prompt: str, input_data: dict[str, Any]) -> str:
        brand_name = str(input_data.get("brand_name") or "Company")
        user_requirements = str(input_data.get("user_requirements") or "").strip()
        image_urls = list(input_data.get("image_urls") or [])
        fallback_asset = image_urls[0] if image_urls else ""
        summary_points = [str(point) for point in input_data.get("summary_points", []) if str(point).strip()]
        hook = summary_points[0] if summary_points else f"{brand_name}의 브랜드 가치를 소개합니다."
        strength = summary_points[1] if len(summary_points) > 1 else hook
        concept_suffix = f" - {user_requirements[:60]}" if user_requirements else ""
        mood = self._infer_bgm_mood(user_requirements)
        target_audience = user_requirements[:80] if user_requirements else "potential customers and partners"
        cta_caption = self._infer_cta_caption(brand_name, user_requirements)

        storyboard = {
            "video_metadata": {
                "concept": f"{brand_name} 브랜드 소개{concept_suffix}",
                "bgm_mood": mood,
                "target_audience": target_audience,
            },
            "scenes": [
                {
                    "scene_number": 1,
                    "duration": "0~3s",
                    "section": "HOOK",
                    "matched_asset": image_urls[0] if len(image_urls) > 0 else fallback_asset,
                    "camera_effect": "Zoom-in",
                    "caption": f"{brand_name}, 한눈에 보는 브랜드",
                    "tts_script": self._merge_requirement_hint(hook, user_requirements),
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
                    "caption": cta_caption,
                    "tts_script": f"{brand_name}의 더 많은 이야기를 지금 확인해보세요.",
                },
            ],
            "recommended_hashtags": ["#Brand", "#CorporateVideo", "#Promotion"],
        }
        return json.dumps(storyboard, ensure_ascii=False)

    def _infer_bgm_mood(self, user_requirements: str) -> str:
        lowered_requirements = user_requirements.lower()
        if any(keyword in lowered_requirements for keyword in ("고급", "럭셔리", "프리미엄", "premium", "luxury")):
            return "luxury elegant premium"
        if any(keyword in lowered_requirements for keyword in ("활기", "밝", "경쾌", "energetic", "bright")):
            return "bright energetic corporate"
        if any(keyword in lowered_requirements for keyword in ("차분", "잔잔", "신뢰", "calm", "trust")):
            return "calm trustworthy corporate"
        return "modern clean corporate"

    def _infer_cta_caption(self, brand_name: str, user_requirements: str) -> str:
        if "예약" in user_requirements:
            return "지금 예약하고 경험해보세요"
        if "문의" in user_requirements:
            return "지금 문의하고 시작하세요"
        if "방문" in user_requirements:
            return "지금 방문해 더 알아보세요"
        return f"{brand_name}와 함께 시작하세요"

    def _merge_requirement_hint(self, script: str, user_requirements: str) -> str:
        if not user_requirements:
            return script[:120]
        return f"{script[:80]} {user_requirements[:40]}".strip()[:120]


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
    raise RuntimeError(f"지원하지 않는 director 프로바이더입니다: {provider_name}")
