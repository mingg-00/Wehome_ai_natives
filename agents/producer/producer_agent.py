from __future__ import annotations

import base64
import os
import re
import time
from typing import Any

import requests

from agents.producer.asset_resolver import AssetResolver
from agents.producer.bgm_agent import BgmSelector
from agents.producer.caption_renderer import CaptionRenderer
from agents.producer.local_video_renderer import LocalVideoRenderer
from agents.producer.providers import create_music_provider, create_tts_provider, create_video_provider
from config.settings import ensure_directories, settings


class ProducerAgent:
    def __init__(
        self,
        assets_dir: str | None = None,
        audio_dir: str | None = None,
        video_dir: str | None = None,
        bgm_dir: str | None = None,
        bgm_volume: float | None = None,
        bgm_selector: BgmSelector | None = None,
        run_number: int | None = None,
        asset_resolver: AssetResolver | None = None,
        caption_renderer: CaptionRenderer | None = None,
        local_video_renderer: LocalVideoRenderer | None = None,
    ) -> None:
        self.assets_dir = assets_dir if assets_dir is not None else settings.assets_dir
        self.audio_dir = audio_dir if audio_dir is not None else settings.audio_dir
        self.video_dir = video_dir if video_dir is not None else settings.video_dir
        self.frame_size = (
            self._even_dimension(settings.local_video_width, 1080),
            self._even_dimension(settings.local_video_height, 1920),
        )
        self.bgm_dir = bgm_dir if bgm_dir is not None else settings.bgm_dir
        self.bgm_volume = bgm_volume if bgm_volume is not None else settings.bgm_volume
        self.run_number = run_number
        self.bgm_selector = bgm_selector if bgm_selector is not None else BgmSelector(self.bgm_dir)
        self.asset_resolver = asset_resolver if asset_resolver is not None else AssetResolver(
            self.assets_dir,
            run_number=self.run_number,
        )
        self.caption_renderer = caption_renderer if caption_renderer is not None else CaptionRenderer()
        self.local_video_renderer = (
            local_video_renderer if local_video_renderer is not None else LocalVideoRenderer()
        )
        self.video_provider = create_video_provider(settings.video_provider)
        self.tts_provider = create_tts_provider(settings.tts_provider)
        self.music_provider = create_music_provider(settings.music_provider)
        ensure_directories(self.assets_dir, self.audio_dir, self.video_dir, self.bgm_dir)

    def render_video(self, storyboard: dict[str, Any], output_filename: str = "wehome_promo_output.mp4") -> str:
        print(f"[ProducerAgent] 비디오 provider 호출: {self.video_provider.name}")
        return self.video_provider.render_video(self, storyboard, output_filename)

    def _render_video_locally(self, storyboard: dict[str, Any], output_filename: str = "wehome_promo_output.mp4") -> str:
        return self.local_video_renderer.render_video(self, storyboard, output_filename)

    def _render_video_with_veo(self, storyboard: dict[str, Any], output_filename: str) -> str:
        if not settings.veo_api_key:
            raise RuntimeError("VEO_API_KEY 또는 GEMINI_API_KEY가 설정되지 않았습니다.")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("VIDEO_PROVIDER=veo를 사용하려면 google-genai가 필요합니다. requirements.txt를 설치하세요.") from exc

        output_filename = self.build_numbered_filename(output_filename)
        output_video_path = os.path.join(self.video_dir, output_filename)
        prompt = self._build_veo_prompt(storyboard)
        client = genai.Client(api_key=settings.veo_api_key)
        config = types.GenerateVideosConfig(
            number_of_videos=1,
            aspect_ratio=settings.veo_aspect_ratio,
            resolution=settings.veo_resolution,
            duration_seconds=settings.veo_duration_seconds,
        )
        operation = client.models.generate_videos(
            model=settings.veo_model,
            prompt=prompt,
            config=config,
        )

        started_at = time.monotonic()
        while not operation.done:
            if time.monotonic() - started_at > settings.veo_timeout_seconds:
                raise RuntimeError("Veo 영상 생성 시간이 초과되었습니다.")
            print("[ProducerAgent] Veo 영상 생성이 끝나기를 기다리는 중...")
            time.sleep(settings.veo_poll_interval_seconds)
            operation = client.operations.get(operation)

        video = operation.response.generated_videos[0].video
        client.files.download(file=video)
        video.save(output_video_path)
        return output_video_path

    def generate_audio(self, tts_text: str, scene_number: int) -> str:
        if self.run_number is not None:
            audio_filename = f"audio_{self.run_number:03d}_scene_{scene_number:02d}.mp3"
        else:
            audio_filename = f"audio_{scene_number}.mp3"
        audio_path = os.path.join(self.audio_dir, audio_filename)
        print(f"[ProducerAgent] TTS provider 호출: {self.tts_provider.name} (장면 {scene_number})")
        return self.tts_provider.generate_audio(tts_text, audio_path)

    def resolve_bgm_path(self, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        print(f"[ProducerAgent] 음악 provider 호출: {self.music_provider.name}")
        return self.music_provider.resolve_bgm_path(self, storyboard, duration_seconds)

    def _generate_music_with_external_api(self, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        if not settings.music_api_url:
            return None
        if not settings.music_api_key:
            raise RuntimeError("MUSIC_API_KEY, SUDO_API_KEY 또는 SUNO_API_KEY가 설정되지 않았습니다.")

        mood = str(storyboard.get("video_metadata", {}).get("bgm_mood", "modern upbeat corporate"))
        concept = str(storyboard.get("video_metadata", {}).get("concept", "company promotional video"))
        prompt = f"{concept}. Instrumental background music, {mood}, clean corporate advertising style, no vocals."
        bgm_filename = (
            f"generated_bgm_{self.run_number:03d}.mp3"
            if self.run_number is not None
            else "generated_bgm.mp3"
        )
        output_path = os.path.join(self.audio_dir, bgm_filename)
        response = requests.post(
            settings.music_api_url,
            headers={
                "Authorization": f"Bearer {settings.music_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.music_model,
                "prompt": prompt,
                "duration_seconds": max(8, int(duration_seconds)),
                "instrumental": True,
            },
            timeout=settings.veo_timeout_seconds,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("audio/") or content_type == "application/octet-stream":
            with open(output_path, "wb") as file_handle:
                file_handle.write(response.content)
            return output_path

        try:
            response_json = response.json()
        except ValueError:
            return None

        audio_url = self._first_present(
            response_json,
            ["audio_url", "audioUrl", "url", "file_url", "fileUrl", "download_url", "downloadUrl"],
        )
        if audio_url:
            self._download_file(str(audio_url), output_path, api_key=settings.music_api_key)
            return output_path

        audio_base64 = self._first_present(response_json, ["audio_base64", "audioBase64", "audio_content"])
        if audio_base64:
            with open(output_path, "wb") as file_handle:
                file_handle.write(base64.b64decode(str(audio_base64)))
            return output_path

        return None

    def build_numbered_filename(self, base_filename: str) -> str:
        base_name, extension = os.path.splitext(base_filename)
        if self.run_number is not None:
            return f"{base_name}_{self.run_number:03d}{extension}"

        pattern = re.compile(rf"^{re.escape(base_name)}_(\d{{3}}){re.escape(extension)}$")
        existing_numbers: list[int] = []
        for file_name in os.listdir(self.video_dir):
            match = pattern.match(file_name)
            if match:
                existing_numbers.append(int(match.group(1)))

        next_number = (max(existing_numbers) + 1) if existing_numbers else 1
        return f"{base_name}_{next_number:03d}{extension}"

    def build_temp_audio_filename(self) -> str:
        if self.run_number is not None:
            return f"temp_audio_{self.run_number:03d}.m4a"
        return "temp_audio.m4a"

    @staticmethod
    def _even_dimension(value: int, fallback: int) -> int:
        dimension = value if value > 0 else fallback
        return dimension if dimension % 2 == 0 else dimension + 1

    def _build_veo_prompt(self, storyboard: dict[str, Any]) -> str:
        metadata = storyboard.get("video_metadata", {})
        lines = [
            "Create a polished vertical corporate promotional video for a Korean brand.",
            f"Concept: {metadata.get('concept', 'company brand introduction')}",
            f"Target audience: {metadata.get('target_audience', 'potential customers and partners')}",
            "Style: premium, trustworthy, modern, clean, brand-safe, cinematic advertising.",
            "Include natural Korean narration timing cues and subtle background music.",
            "Storyboard scenes:",
        ]
        for scene in storyboard.get("scenes", []):
            lines.append(
                "- "
                f"{scene.get('section', 'SCENE')} | "
                f"caption: {scene.get('caption', '')} | "
                f"narration: {scene.get('tts_script', '')} | "
                f"camera: {scene.get('camera_effect', '')}"
            )
        return "\n".join(lines)

    def _download_file(self, url: str, output_path: str, api_key: str | None = None) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        with requests.get(url, headers=headers, stream=True, timeout=settings.request_timeout_seconds) as response:
            response.raise_for_status()
            with open(output_path, "wb") as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file_handle.write(chunk)

    @staticmethod
    def _first_present(data: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            value = data.get(key)
            if value:
                return value
        return None
