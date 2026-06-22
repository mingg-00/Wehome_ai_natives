from __future__ import annotations                   # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화

import os                                            # 파일 경로 처리를 위해 표준 라이브러리의 os 모듈을 사용
from typing import Any, Protocol                     # Any 타입과 Protocol을 사용하여 프로바이더 인터페이스를 정의

import numpy as np                                   # 무음 오디오 생성을 위해 NumPy를 사용
import requests                                      # 외부 API 호출을 위해 requests 라이브러리를 사용
from gtts import gTTS                                # Google Text-to-Speech를 사용하여 TTS 기능을 제공
from moviepy.audio.AudioClip import AudioArrayClip   # 무음 오디오 생성을 위해 MoviePy의 AudioArrayClip 사용

from config.settings import settings                 # 애플리케이션 설정을 가져오기 위해 config.settings 모듈에서 settings 객체를 가져옴


# 비디오 렌더링을 담당하는 프로바이더 인터페이스를 정의
class VideoProvider(Protocol):
    name: str

    def render_video(self, agent: Any, storyboard: dict[str, Any], output_filename: str) -> str:
        ...


# 텍스트를 받아 오디오 파일을 생성하는 메서드를 정의
class TTSProvider(Protocol):
    name: str

    def generate_audio(self, tts_text: str, audio_path: str) -> str:
        ...


# 스토리보드와 지속 시간에 따라 BGM 경로를 반환하는 메서드를 정의
class MusicProvider(Protocol):
    name: str

    def resolve_bgm_path(self, agent: Any, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        ...


# 로컬 파일 시스템에서 BGM 트랙을 선택하는 프로바이더 클래스
class MoviePyLocalVideoProvider:
    name = "local"

    def render_video(self, agent: Any, storyboard: dict[str, Any], output_filename: str) -> str:
        return agent._render_video_locally(storyboard, output_filename)


# Veo API를 사용하여 비디오를 렌더링하는 프로바이더 클래스
class VeoVideoProvider:
    name = "veo"

    def render_video(self, agent: Any, storyboard: dict[str, Any], output_filename: str) -> str:
        return agent._render_video_with_veo(storyboard, output_filename)


# Google TTS를 사용하여 텍스트를 오디오로 변환하는 프로바이더 클래스
class GttsTTSProvider:
    name = "gtts"

    def generate_audio(self, tts_text: str, audio_path: str) -> str:
        tts = gTTS(text=tts_text, lang="ko")
        tts.save(audio_path)
        return audio_path


# ElevenLabs API를 사용하여 텍스트를 오디오로 변환하는 프로바이더 클래스
class ElevenLabsTTSProvider:
    name = "elevenlabs"

    def generate_audio(self, tts_text: str, audio_path: str) -> str:
        if not settings.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY가 설정되지 않았습니다.")

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


# 무음 TTS 프로바이더로, 텍스트 길이에 따라 적절한 길이의 무음 오디오 파일을 생성하여 반환
class LocalSilentTTSProvider:
    name = "local_silent"

    def generate_audio(self, tts_text: str, audio_path: str) -> str:
        duration_seconds = max(1.2, min(4.0, len(tts_text) / 18))
        fps = 44100
        samples = np.zeros((max(1, int(duration_seconds * fps)), 1), dtype=np.float32)
        silent_clip = AudioArrayClip(samples, fps=fps)
        try:
            silent_clip.write_audiofile(audio_path, fps=fps, codec="libmp3lame", logger=None)
        finally:
            silent_clip.close()
        return audio_path


# 스토리보드의 분위기에 맞는 BGM 트랙을 로컬 라이브러리에서 선택하는 프로바이더 클래스
class LocalMusicProvider:
    name = "local"

    def resolve_bgm_path(self, agent: Any, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        return agent.bgm_selector.select_bgm_path(storyboard)


# 외부 API를 사용하여 BGM 트랙을 생성하거나, 실패할 경우 로컬 라이브러리에서 선택하는 프로바이더 클래스
class ExternalAPIMusicProvider:
    name = "api"

    def resolve_bgm_path(self, agent: Any, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        generated_path = agent._generate_music_with_external_api(storyboard, duration_seconds)
        if generated_path:
            return generated_path
        print("[ProducerAgent] 외부 음악 생성을 사용할 수 없어 로컬 BGM 라이브러리로 대체합니다.")
        return agent.bgm_selector.select_bgm_path(storyboard)


# 비디오 프로바이더 팩토리 함수로, 설정된 프로바이더 이름에 따라 적절한 VideoProvider 인스턴스를 생성하여 반환
def create_video_provider(provider_name: str) -> VideoProvider:
    normalized_provider = provider_name.lower()
    if normalized_provider == "local":
        return MoviePyLocalVideoProvider()
    if normalized_provider == "veo":
        return VeoVideoProvider()
    raise RuntimeError(f"지원하지 않는 비디오 프로바이더입니다: {provider_name}")


# TTS 프로바이더 팩토리 함수로, 설정된 프로바이더 이름에 따라 적절한 TTSProvider 인스턴스를 생성하여 반환
def create_tts_provider(provider_name: str) -> TTSProvider:
    normalized_provider = provider_name.lower()
    if normalized_provider == "gtts":
        return GttsTTSProvider()
    if normalized_provider == "elevenlabs":
        return ElevenLabsTTSProvider()
    if normalized_provider in {"silent", "local_silent"}:
        return LocalSilentTTSProvider()
    raise RuntimeError(f"지원하지 않는 TTS 프로바이더입니다: {provider_name}")


# 음악 프로바이더 팩토리 함수로, 설정된 프로바이더 이름에 따라 적절한 MusicProvider 인스턴스를 생성하여 반환
def create_music_provider(provider_name: str) -> MusicProvider:
    normalized_provider = provider_name.lower()
    if normalized_provider == "local":
        return LocalMusicProvider()
    if normalized_provider in {"sudo", "suno", "api"}:
        return ExternalAPIMusicProvider()
    raise RuntimeError(f"지원하지 않는 음악 프로바이더입니다: {provider_name}")
