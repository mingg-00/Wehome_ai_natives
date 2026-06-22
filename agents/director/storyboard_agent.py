from __future__ import annotations   # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화
 
import json                          # JSON 파싱과 직렬화를 위해 표준 라이브러리의 json 모듈을 사용
import hashlib                       # 입력 데이터 기반 캐시 키를 만들기 위해 해시 함수를 사용
import os                            # 파일 경로 처리를 위해 표준 라이브러리의 os 모듈을 사용
import re                            # 정규 표현식을 사용해 모델 응답에서 코드펜스를 제거
import time                          # 재시도 간격을 구현하기 위해 표준 라이브러리의 time 모듈을 사용
from datetime import date            # 외부 API 일일 호출 한도를 계산하기 위해 날짜를 사용
from typing import Any               # Any 타입을 사용하여 스토리보드의 구조를 유연하게 처리

import requests                      # HTTP 요청을 보내고 응답을 처리하기 위해 requests 라이브러리를 사용

from agents.director.providers import DirectorProvider, create_director_provider
from config.settings import ensure_directories, settings, write_json_atomic  # 설정에서 provider, 요청 타임아웃, 캐시 경로 등을 읽어옴


# 스토리보드 관련 예외를 정의해 API 호출과 스키마 검증에서 발생하는 오류를 구분
class StoryboardError(RuntimeError):
    pass


# 스토리보드 API 호출 실패를 나타내는 예외
class StoryboardAPIError(StoryboardError):
    pass


# 스토리보드 스키마 검증 실패를 나타내는 예외
class StoryboardSchemaError(StoryboardError):
    pass


# 스토리보드 생성과 검증을 담당하는 에이전트 클래스
class StoryboardAgent:
    retry_attempts: int = 3               # API 요청 실패 시 재시도 횟수
    retry_backoff_seconds: float = 1.5    # 재시도 간격을 선형적으로 증가시키는 백오프 시간(초 단위)

    # 생성자에서 API 키, 모델 이름, API URL, 캐시 경로, 타임아웃, 세션 등을 설정. 필요한 경우 기본값을 settings에서 읽어옴
    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        api_url: str | None = None,
        cache_path: str | None = None,
        timeout_seconds: int | None = None,
        session: requests.Session | None = None,
        provider: DirectorProvider | None = None,
        run_number: int | None = None,
    ) -> None:
        self.provider = provider or create_director_provider(
            settings.director_provider,
            api_key=api_key,
            model_name=model_name,
            api_url=api_url,
            timeout_seconds=timeout_seconds,
            session=session,
        )
        self.provider_name = self.provider.name
        self.cache_path = cache_path if cache_path is not None else settings.storyboard_cache_path
        self.run_number = run_number
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.request_timeout_seconds
        self.fallback_provider = self._create_fallback_provider(session=session)
        self.retry_attempts = settings.storyboard_retry_attempts if settings.storyboard_retry_attempts > 0 else 3
        self.retry_backoff_seconds = (
            settings.storyboard_retry_backoff_seconds
            if settings.storyboard_retry_backoff_seconds > 0
            else 1.5
        )

        # 캐시 파일이 있는 위치를 먼저 보장해 두면, 이후 재사용이 쉬워짐
        cache_dir = os.path.dirname(self.cache_path)
        if cache_dir:
            ensure_directories(cache_dir)

    # 외부 API 실패나 한도 초과 시 사용할 안전한 대체 provider를 만든다.
    def _create_fallback_provider(self, session: requests.Session | None = None) -> DirectorProvider | None:
        if not settings.director_fallback_enabled:
            return None

        fallback_name = settings.director_fallback_provider.strip()
        if not fallback_name or fallback_name.lower() == self.provider_name.lower():
            return None

        return create_director_provider(
            fallback_name,
            timeout_seconds=self.timeout_seconds,
            session=session,
        )

    # 스토리보드를 생성하는 메인 메서드로, 캐시 사용 여부와 강제 갱신 옵션을 받아 처리
    def generate_storyboard(
        self,
        input_data: dict[str, Any],
        use_cache: bool | None = None,
        force_refresh: bool | None = None,
    ) -> dict[str, Any]:
        cache_enabled = settings.storyboard_cache_enabled if use_cache is None else use_cache
        refresh_requested = settings.storyboard_force_refresh if force_refresh is None else force_refresh

        # 캐시가 유효하면 provider를 다시 호출하지 않고 바로 재사용
        if cache_enabled and not refresh_requested:
            cached_storyboard = self.load_cached_storyboard(input_data)
            if cached_storyboard is not None:
                self._save_run_cache_copy(cached_storyboard, input_data)
                return cached_storyboard

        # 캐시가 없거나 갱신이 필요할 때만 외부 API를 호출
        storyboard = self._request_storyboard(input_data)
        if cache_enabled:
            self.save_storyboard_cache(storyboard, input_data)
        return storyboard

    # 캐시 파일에서 스토리보드를 읽어오는 메서드
    def load_cached_storyboard(self, input_data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        cache_path = self._find_cached_storyboard_path(input_data)

        # 캐시 파일이 없으면 단순히 None을 반환해 다음 단계로 넘김
        if cache_path is None or not os.path.exists(cache_path):
            return None

        with open(cache_path, "r", encoding="utf-8") as file_handle:
            cached_storyboard = json.load(file_handle)

        # 캐시도 동일한 스키마 검증을 통과해야 안전하게 재사용할 수 있음
        allowed_assets = input_data.get("image_urls", []) if input_data else []
        self.validate_storyboard_schema(cached_storyboard, allowed_assets=allowed_assets)
        print(f"[StoryboardAgent] 스토리보드 캐시 재사용: {cache_path}", flush=True)
        return cached_storyboard

    # 스토리보드를 캐시 파일에 저장하는 메서드
    def save_storyboard_cache(self, storyboard: dict[str, Any], input_data: dict[str, Any] | None = None) -> None:
        cache_path = self._build_input_cache_path(input_data)

        # 렌더링 실패와 별개로 재사용 가능한 중간 산출물을 파일에 보관
        write_json_atomic(cache_path, storyboard, ensure_ascii=False, indent=2)
        print(f"[StoryboardAgent] 스토리보드 캐시 저장 완료: {cache_path}", flush=True)

    # 입력 데이터가 같을 때만 같은 캐시를 쓰도록 안정적인 해시 기반 경로를 만든다.
    def _build_input_cache_path(self, input_data: dict[str, Any] | None = None) -> str:
        if input_data is None:
            return self.cache_path

        cache_dir = self._cache_dir()
        cache_key = self._build_input_cache_key(input_data)
        if self.run_number is not None:
            return os.path.join(cache_dir, f"storyboard_{self.run_number:03d}_{cache_key}.json")
        return os.path.join(cache_dir, f"storyboard_{cache_key}.json")

    def _find_cached_storyboard_path(self, input_data: dict[str, Any] | None = None) -> str | None:
        if input_data is None:
            return self.cache_path if os.path.exists(self.cache_path) else None

        current_run_path = self._build_input_cache_path(input_data)
        if os.path.exists(current_run_path):
            return current_run_path

        cache_dir = self._cache_dir()
        cache_key = self._build_input_cache_key(input_data)
        legacy_path = os.path.join(cache_dir, f"storyboard_{cache_key}.json")
        if os.path.exists(legacy_path):
            return legacy_path

        if not os.path.isdir(cache_dir):
            return None

        pattern = re.compile(rf"^storyboard_(\d{{3}})_{re.escape(cache_key)}\.json$")
        candidates: list[tuple[int, str]] = []
        for entry_name in os.listdir(cache_dir):
            match = pattern.match(entry_name)
            if match:
                candidates.append((int(match.group(1)), os.path.join(cache_dir, entry_name)))

        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]

    def _save_run_cache_copy(self, storyboard: dict[str, Any], input_data: dict[str, Any] | None) -> None:
        if self.run_number is None or input_data is None:
            return

        cache_path = self._build_input_cache_path(input_data)
        if os.path.exists(cache_path):
            return
        self.save_storyboard_cache(storyboard, input_data)

    # JSON 정렬 직렬화를 사용해 입력 순서 차이로 캐시가 흔들리지 않게 한다.
    def _build_input_cache_key(self, input_data: dict[str, Any]) -> str:
        normalized_input = json.dumps(input_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized_input.encode("utf-8")).hexdigest()[:12]

    # 기존 STORYBOARD_CACHE_PATH가 파일 경로여도 그 이름을 캐시 폴더 이름으로 재사용한다.
    def _cache_dir(self) -> str:
        cache_root, cache_extension = os.path.splitext(self.cache_path)
        if cache_extension:
            return cache_root
        return self.cache_path

    # 선택된 provider에 스토리보드 생성을 요청하는 내부 메서드로, 재시도 로직과 응답 파싱을 포함
    def _request_storyboard(self, input_data: dict[str, Any]) -> dict[str, Any]:
        prompt = build_storyboard_prompt(input_data)
        try:
            return self._request_storyboard_from_provider(self.provider, prompt, input_data)
        except StoryboardAPIError as exc:
            if self.fallback_provider is None:
                raise
            print(
                f"[StoryboardAgent] {self.provider_name} 사용 불가. "
                f"{self.fallback_provider.name}(으)로 대체합니다: {exc}",
                flush=True,
            )
            return self._request_storyboard_from_provider(self.fallback_provider, prompt, input_data)

    def _request_storyboard_from_provider(
        self,
        provider: DirectorProvider,
        prompt: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        provider_name = provider.name
        print(f"[StoryboardAgent] director provider 호출: {provider_name}", flush=True)
        self._reserve_director_api_call(provider_name)
        # 재시도 로직을 구현해 일시적인 네트워크 오류나 API 제한으로 인한 실패를 완화
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                raw_text = provider.request_storyboard_text(prompt, input_data)
                break
            except requests.HTTPError as exc:
                response = exc.response
                status_code = response.status_code if response is not None else None
                retryable_statuses = {429, 500, 502, 503, 504}
                if status_code == 429:
                    raise StoryboardAPIError(f"{provider_name} API 할당량 또는 요청 제한에 도달했습니다: HTTP 429") from exc
                if status_code in retryable_statuses and attempt < self.retry_attempts:
                    wait_seconds = self.retry_backoff_seconds * attempt
                    print(
                        f"[StoryboardAgent] {provider_name} 요청 재시도 {attempt}/{self.retry_attempts}: HTTP {status_code}, {wait_seconds:.1f}초 대기",
                        flush=True,
                    )
                    time.sleep(wait_seconds)
                    last_error = exc
                    continue

                if response is not None:
                    raise StoryboardAPIError(
                        f"{provider_name} API 요청 실패: {response.status_code} {response.reason}"
                    ) from exc
                raise StoryboardAPIError(f"{provider_name} API 요청 실패: HTTP 오류") from exc
            except requests.RequestException as exc:
                if attempt < self.retry_attempts:
                    wait_seconds = self.retry_backoff_seconds * attempt
                    print(
                        f"[StoryboardAgent] {provider_name} 요청 재시도 {attempt}/{self.retry_attempts}: {exc.__class__.__name__}, {wait_seconds:.1f}초 대기",
                        flush=True,
                    )
                    time.sleep(wait_seconds)
                    last_error = exc
                    continue
                raise StoryboardAPIError(f"{provider_name} API 요청 실패: {exc.__class__.__name__}") from exc
            except RuntimeError as exc:
                raise StoryboardAPIError(str(exc)) from exc

        else:
            if last_error is not None:
                raise StoryboardAPIError(f"{provider_name} API 요청이 {self.retry_attempts}회 시도 후 실패했습니다: {last_error}") from last_error
            raise StoryboardAPIError(f"{provider_name} API 요청이 {self.retry_attempts}회 시도 후 실패했습니다.")

        storyboard = self.parse_storyboard_text(raw_text, input_data.get("image_urls", []))
        return storyboard

    # 무료 API 한도 보호를 위해 외부 director provider의 일일 호출 시도 수를 파일에 기록한다.
    def _reserve_director_api_call(self, provider_name: str) -> None:
        if provider_name in {"local", "local_template", "template"}:
            return
        if settings.director_daily_api_limit <= 0:
            return

        usage_path = settings.director_api_usage_path
        usage_dir = os.path.dirname(usage_path)
        if usage_dir:
            ensure_directories(usage_dir)

        today = date.today().isoformat()
        usage_data: dict[str, Any] = {}
        if os.path.exists(usage_path):
            try:
                with open(usage_path, "r", encoding="utf-8") as file_handle:
                    loaded_data = json.load(file_handle)
                if isinstance(loaded_data, dict):
                    usage_data = loaded_data
            except (OSError, json.JSONDecodeError):
                usage_data = {}

        if usage_data.get("date") != today:
            usage_data = {"date": today, "providers": {}}

        providers = usage_data.setdefault("providers", {})
        provider_count = int(providers.get(provider_name, 0))
        if provider_count >= settings.director_daily_api_limit:
            raise StoryboardAPIError(
                f"{provider_name} 일일 API 호출 한도에 도달했습니다 "
                f"({provider_count}/{settings.director_daily_api_limit})."
            )

        providers[provider_name] = provider_count + 1
        write_json_atomic(usage_path, usage_data, ensure_ascii=False, indent=2)

    # 모델 응답에서 코드펜스가 포함된 경우에도 JSON 파싱이 가능하도록 텍스트를 정리한 후, 스토리보드 스키마 검증을 수행
    def parse_storyboard_text(self, raw_text: str, allowed_assets: list[str] | None = None) -> dict[str, Any]:
        # 모델이 실수로 코드펜스를 붙여도 JSON 파싱이 되도록 먼저 정리
        cleaned_text = self._strip_code_fences(raw_text)
        try:
            storyboard = json.loads(cleaned_text)
        except json.JSONDecodeError as exc:
            raise StoryboardSchemaError(f"스토리보드 응답이 유효한 JSON이 아닙니다: {exc}") from exc

        # 파싱 직후 스키마 검증을 통과해야 다음 단계가 안정적으로 동작
        self.validate_storyboard_schema(storyboard, allowed_assets=allowed_assets or [])
        return storyboard

    # 스토리보드가 예상한 구조와 타입을 갖추었는지 검증하는 메서드로, 필요한 경우 매칭된 자산을 허용된 목록 내에서 보정
    def validate_storyboard_schema(
        self,
        storyboard: dict[str, Any],
        allowed_assets: list[str] | None = None,
    ) -> None:
        # 최상위 구조부터 확인해야 이후 단계에서 KeyError를 줄일 수 있음
        if not isinstance(storyboard, dict):
            raise StoryboardSchemaError("스토리보드는 JSON 객체여야 합니다.")

        required_top_level_keys = {"video_metadata", "scenes", "recommended_hashtags"}
        missing_keys = required_top_level_keys - set(storyboard)
        if missing_keys:
            raise StoryboardSchemaError(f"스토리보드에 필수 키가 없습니다: {sorted(missing_keys)}")

        video_metadata = storyboard.get("video_metadata")
        scenes = storyboard.get("scenes")
        hashtags = storyboard.get("recommended_hashtags")

        if not isinstance(video_metadata, dict):
            raise StoryboardSchemaError("video_metadata는 객체여야 합니다.")
        if not isinstance(scenes, list) or not scenes:
            raise StoryboardSchemaError("scenes는 비어 있지 않은 리스트여야 합니다.")
        if not isinstance(hashtags, list):
            raise StoryboardSchemaError("recommended_hashtags는 리스트여야 합니다.")

        required_scene_keys = {
            "scene_number",
            "duration",
            "section",
            "matched_asset",
            "camera_effect",
            "caption",
            "tts_script",
        }

        normalized_allowed_assets = list(allowed_assets or [])
        for index, scene in enumerate(scenes):
            # 각 Scene은 렌더링 모듈이 바로 읽을 수 있는 최소 필드를 가져야 한다.
            if not isinstance(scene, dict):
                raise StoryboardSchemaError(f"{index + 1}번 장면은 객체여야 합니다.")
            missing_scene_keys = required_scene_keys - set(scene)
            if missing_scene_keys:
                raise StoryboardSchemaError(
                    f"{index + 1}번 장면에 필수 키가 없습니다: {sorted(missing_scene_keys)}"
                )
            if not normalized_allowed_assets:
                continue
            # 매칭된 이미지가 입력 목록 밖으로 벗어나면 안전한 대체 자산으로 보정한다.
            if scene["matched_asset"] not in normalized_allowed_assets:
                fallback_asset = normalized_allowed_assets[index % len(normalized_allowed_assets)]
                scene["matched_asset"] = fallback_asset

        self._ensure_string_fields(video_metadata, ["concept", "bgm_mood", "target_audience"])
        for scene in scenes:
            self._ensure_string_fields(
                scene,
                ["duration", "section", "matched_asset", "camera_effect", "caption", "tts_script"],
            )
            if not isinstance(scene.get("scene_number"), int):
                raise StoryboardSchemaError("scene_number는 정수여야 합니다.")

    # 모델 응답에 섞일 수 있는 마크다운 코드펜스를 제거하는 메서드로, JSON 파싱이 방해받지 않도록 텍스트를 정리
    def _strip_code_fences(self, raw_text: str) -> str:
        stripped_text = raw_text.strip()
        stripped_text = re.sub(r"^```(?:json)?\s*", "", stripped_text, flags=re.IGNORECASE)
        stripped_text = re.sub(r"\s*```$", "", stripped_text)
        return stripped_text.strip()

    # 스키마의 텍스트 필드는 렌더링과 캡션 조합에서 바로 사용할 수 있어야 함. 각 필드가 문자열인지 확인하고, 그렇지 않으면 예외를 발생시킴
    def _ensure_string_fields(self, data: dict[str, Any], field_names: list[str]) -> None:
        for field_name in field_names:
            if not isinstance(data.get(field_name), str):
                raise StoryboardSchemaError(f"{field_name} 필드는 문자열이어야 합니다.")

# 스토리보드 프롬프트를 생성하는 함수로, 회사 프로필 데이터를 받아 provider에 전달할 텍스트 프롬프트를 구성
def build_storyboard_prompt(input_data: dict[str, Any]) -> str:
        user_requirements = str(input_data.get("user_requirements") or "").strip()
        requirements_section = (
            user_requirements
            if user_requirements
            else "No additional user requirements were provided. Infer the best direction from the company profile."
        )
        return f"""You are a data-driven short-form video marketing agent for company branding videos.
Your task is to analyze the input company profile and generate a structured storyboard JSON for corporate promotional video production.
Return only pure JSON. Do not include markdown fences, greetings, explanations, or any extra text.

[Core Guidelines]
1. Extract at least two clear strengths or differentiators from the company profile.
2. Create a strong hook for the first 3 seconds.
3. Match each scene to one image URL from image_urls only.
4. Keep the tone professional, modern, and brand-safe.
5. Follow the output schema exactly.
6. Treat the user's natural-language requirements as priority direction for concept, tone, target audience, captions, TTS scripts, CTA, and bgm_mood.
7. If the user requirements conflict with crawled website content, keep factual company information accurate but adapt the presentation style to the user requirements.

[Output Schema]
{{
    "video_metadata": {{
        "concept": "text",
        "bgm_mood": "text",
        "target_audience": "text"
    }},
    "scenes": [
        {{
            "scene_number": 1,
            "duration": "0~3s",
            "section": "HOOK",
            "matched_asset": "image filename or URL",
            "camera_effect": "Zoom-in",
            "caption": "text",
            "tts_script": "text"
        }}
    ],
    "recommended_hashtags": ["#Brand", "#CorporateVideo", "#Promotion"]
}}

[User Requirements]
{requirements_section}

[Company Profile Data]
{json.dumps(input_data, ensure_ascii=False, indent=2)}
"""
