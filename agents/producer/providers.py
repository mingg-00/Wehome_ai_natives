from __future__ import annotations

import os
from typing import Any, Protocol

import requests
from gtts import gTTS
from moviepy.audio.AudioClip import AudioClip

from config.settings import settings


class VideoProvider(Protocol):
    name: str

    def render_video(self, agent: Any, storyboard: dict[str, Any], output_filename: str) -> str:
        ...


class TTSProvider(Protocol):
    name: str

    def generate_audio(self, tts_text: str, audio_path: str) -> str:
        ...


class MusicProvider(Protocol):
    name: str

    def resolve_bgm_path(self, agent: Any, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        ...


class MoviePyLocalVideoProvider:
    name = "local"

    def render_video(self, agent: Any, storyboard: dict[str, Any], output_filename: str) -> str:
        return agent._render_video_locally(storyboard, output_filename)


class VeoVideoProvider:
    name = "veo"

    def render_video(self, agent: Any, storyboard: dict[str, Any], output_filename: str) -> str:
        return agent._render_video_with_veo(storyboard, output_filename)


class GttsTTSProvider:
    name = "gtts"

    def generate_audio(self, tts_text: str, audio_path: str) -> str:
        tts = gTTS(text=tts_text, lang="ko")
        tts.save(audio_path)
        return audio_path


class ElevenLabsTTSProvider:
    name = "elevenlabs"

    def generate_audio(self, tts_text: str, audio_path: str) -> str:
        if not settings.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured.")

        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
            f"?output_format={settings.elevenlabs_output_format}"
        )
        response = requests.post(
            url,
            headers={
                "xi-api-key": settings.elevenlabs_api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": tts_text,
                "model_id": settings.elevenlabs_model_id,
            },
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        with open(audio_path, "wb") as file_handle:
            file_handle.write(response.content)
        return audio_path


class LocalSilentTTSProvider:
    name = "local_silent"

    def generate_audio(self, tts_text: str, audio_path: str) -> str:
        duration_seconds = max(1.2, min(4.0, len(tts_text) / 18))
        silent_clip = AudioClip(lambda t: 0, duration=duration_seconds, fps=44100)
        try:
            silent_clip.write_audiofile(audio_path, fps=44100, codec="libmp3lame", verbose=False, logger=None)
        finally:
            silent_clip.close()
        return audio_path


class LocalMusicProvider:
    name = "local"

    def resolve_bgm_path(self, agent: Any, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        return agent.bgm_selector.select_bgm_path(storyboard)


class ExternalAPIMusicProvider:
    name = "api"

    def resolve_bgm_path(self, agent: Any, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        generated_path = agent._generate_music_with_external_api(storyboard, duration_seconds)
        if generated_path:
            return generated_path
        print("[ProducerAgent] External music generation unavailable. Falling back to local BGM library.")
        return agent.bgm_selector.select_bgm_path(storyboard)


def create_video_provider(provider_name: str) -> VideoProvider:
    normalized_provider = provider_name.lower()
    if normalized_provider == "local":
        return MoviePyLocalVideoProvider()
    if normalized_provider == "veo":
        return VeoVideoProvider()
    raise RuntimeError(f"Unsupported video provider: {provider_name}")


def create_tts_provider(provider_name: str) -> TTSProvider:
    normalized_provider = provider_name.lower()
    if normalized_provider == "gtts":
        return GttsTTSProvider()
    if normalized_provider == "elevenlabs":
        return ElevenLabsTTSProvider()
    if normalized_provider in {"silent", "local_silent"}:
        return LocalSilentTTSProvider()
    raise RuntimeError(f"Unsupported TTS provider: {provider_name}")


def create_music_provider(provider_name: str) -> MusicProvider:
    normalized_provider = provider_name.lower()
    if normalized_provider == "local":
        return LocalMusicProvider()
    if normalized_provider in {"sudo", "suno", "api"}:
        return ExternalAPIMusicProvider()
    raise RuntimeError(f"Unsupported music provider: {provider_name}")
