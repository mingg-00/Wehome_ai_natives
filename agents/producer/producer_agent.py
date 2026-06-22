from __future__ import annotations       # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화
 
import hashlib                           # URL에서 파일 이름을 안전하게 생성하기 위해 해시 함수를 사용
import re                                # 파일 이름 패턴을 처리하기 위해 정규 표현식 모듈을 사용
import os                                # 파일 경로 처리를 위해 표준 라이브러리의 os 모듈을 사용
import time                              # 렌더링 시간 측정과 타임아웃 처리를 위해 time 모듈을 사용
from typing import Any                   # Any 타입을 사용하여 스토리보드의 구조를 유연하게 처리
from urllib.parse import urlparse        # URL에서 파일 이름을 추출하기 위해 urllib.parse 모듈의 urlparse 함수를 사용
from urllib.request import urlopen       # URL에서 파일을 다운로드하기 위해 urllib.request 모듈의 urlopen 함수를 사용

import numpy as np                       # 이미지 처리를 위해 NumPy를 사용
import requests                          # 외부 API 호출을 위해 requests 라이브러리를 사용
from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips # 영상과 오디오 처리를 위해 MoviePy 라이브러리에서 필요한 클래스와 함수를 가져온다.
from moviepy.audio.AudioClip import CompositeAudioClip    # 오디오 클립을 합성하기 위해 CompositeAudioClip 클래스를 가져옴
from PIL import Image, ImageDraw, ImageFont               # 자막 이미지를 직접 그리기 위해 Pillow 라이브러리에서 필요한 클래스를 가져옴

from agents.producer.bgm_agent import BgmSelector         # BGM 선택기를 사용하여 스토리보드의 분위기에 맞는 BGM을 선택하기 위해 BgmSelector 클래스를 가져옴
from agents.producer.providers import create_music_provider, create_tts_provider, create_video_provider
from config.settings import ensure_directories, settings  # 설정과 디렉토리 준비 함수를 가져와 애플리케이션 설정과 파일 시스템 관리를 처리


# 스토리보드를 받아 영상과 오디오를 생성하는 역할
class ProducerAgent:

    # 생성자에서 필요한 디렉토리 경로와 BGM 선택기를 초기화하고, 렌더링에 필요한 폴더가 준비되어 있는지 확인
    def __init__(
        self,
        assets_dir: str | None = None,
        audio_dir: str | None = None,
        video_dir: str | None = None,
        bgm_dir: str | None = None,
        bgm_volume: float | None = None,
        bgm_selector: BgmSelector | None = None,
    ) -> None:
        self.assets_dir = assets_dir if assets_dir is not None else settings.assets_dir
        self.audio_dir = audio_dir if audio_dir is not None else settings.audio_dir
        self.video_dir = video_dir if video_dir is not None else settings.video_dir
        self.bgm_dir = bgm_dir if bgm_dir is not None else settings.bgm_dir
        self.bgm_volume = bgm_volume if bgm_volume is not None else settings.bgm_volume
        self.bgm_selector = bgm_selector if bgm_selector is not None else BgmSelector(self.bgm_dir)
        self.video_provider = create_video_provider(settings.video_provider)
        self.tts_provider = create_tts_provider(settings.tts_provider)
        self.music_provider = create_music_provider(settings.music_provider)
        # 영상, 오디오, 에셋 폴더는 렌더링 전에 한 번만 준비하면 된다.
        ensure_directories(self.assets_dir, self.audio_dir, self.video_dir, self.bgm_dir)


    # Windows 시스템에서 사용할 수 있는 글꼴 경로를 찾는다.
    def _find_font_path(self) -> str | None:
        candidate_paths = [
            r"C:\Windows\Fonts\malgun.ttf",
            r"C:\Windows\Fonts\malgunbd.ttf",
            r"C:\Windows\Fonts\gulim.ttc",
            r"C:\Windows\Fonts\nanumgothic.ttf",
            r"C:\Windows\Fonts\NotoSansCJKkr-Regular.otf",
            r"C:\Windows\Fonts\arial.ttf",
        ]
        for candidate_path in candidate_paths:
            if os.path.exists(candidate_path):
                return candidate_path
        return None


    # 스토리보드를 받아 영상과 오디오를 생성
    def render_video(self, storyboard: dict[str, Any], output_filename: str = "wehome_promo_output.mp4") -> str:
        return self.video_provider.render_video(self, storyboard, output_filename)

    # MoviePy 기반 로컬 렌더링 provider가 호출하는 실제 렌더링 구현
    def _render_video_locally(self, storyboard: dict[str, Any], output_filename: str = "wehome_promo_output.mp4") -> str:
        # 스토리보드의 scenes 배열을 순서대로 영상 클립으로 바꿈
        scenes = storyboard.get("scenes", [])
        if not scenes:
            raise RuntimeError("Storyboard does not contain any scenes.")

        rendered_clips = []
        clip_resources = []
        bgm_clip = None
        bgm_mixed_clip = None

        try:
            for scene in scenes:
                # Scene 단위로 처리하면 일부 자산이 빠져도 전체 파이프라인이 덜 깨짐
                scene_clip, clip_resources_for_scene = self._render_scene(scene)
                if scene_clip is None:
                    continue
                rendered_clips.append(scene_clip)
                clip_resources.extend(clip_resources_for_scene)

            if not rendered_clips:
                raise RuntimeError("No renderable scenes were produced.")

            # 클립을 하나로 합치고 최종 MP4를 출력
            final_video = concatenate_videoclips(rendered_clips, method="compose")
            bgm_path = self._resolve_bgm_path(storyboard, float(final_video.duration))
            if bgm_path:
                print(f"[ProducerAgent] Selected BGM: {bgm_path}")
                bgm_clip = AudioFileClip(bgm_path)
                bgm_mixed_clip = bgm_clip.subclip(0, min(float(bgm_clip.duration), float(final_video.duration)))
                bgm_mixed_clip = bgm_mixed_clip.volumex(self.bgm_volume)

                if final_video.audio is not None:
                    final_audio = CompositeAudioClip([final_video.audio, bgm_mixed_clip])
                else:
                    final_audio = bgm_mixed_clip
                final_video = self._set_audio(final_video, final_audio)

            # 이미 존재하는 파일이 있으면 번호를 붙여 덮어쓰기를 방지
            output_filename = self._build_numbered_filename(output_filename)
            output_video_path = os.path.join(self.video_dir, output_filename)
            final_video.write_videofile(
                output_video_path,
                fps=24,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=os.path.join(self.audio_dir, "temp_audio.m4a"),
                remove_temp=True,
                ffmpeg_params=[
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-vf",
                    "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                ],
            )
            final_video.close()
            return output_video_path
        finally:
            # MoviePy 객체는 파일 핸들을 잡을 수 있으므로 작업 후 반드시 정리
            self._close_clips(rendered_clips)
            self._close_clips(clip_resources)
            self._close_clips([clip for clip in [bgm_mixed_clip, bgm_clip] if clip is not None])

    # 장면을 렌더링하는 메서드
    def _render_scene(self, scene: dict[str, Any]):
        asset_name = scene.get("matched_asset", "")
        image_path = self._resolve_image_path(asset_name)
        if image_path is None:
            # 이미지가 없으면 해당 장면만 건너뛰고 전체 렌더링은 계속 진행
            print(f"[ProducerAgent] Missing asset, skipping scene {scene.get('scene_number')}: {asset_name}")
            return None, []

        tts_text = scene.get("tts_script", "")
        if not tts_text:
            # 나레이션 텍스트가 비어 있으면 음성 파일을 만들 수 없으므로 제외
            print(f"[ProducerAgent] Empty TTS text, skipping scene {scene.get('scene_number')}.")
            return None, []

        # 장면별로 음성 파일을 먼저 생성한 뒤, 그 실제 길이에 맞춰 이미지를 맞춤
        audio_path = self._generate_audio(tts_text, int(scene["scene_number"]))
        audio_clip = AudioFileClip(audio_path)
        scene_duration = max(float(audio_clip.duration), 0.1)

        image_clip = ImageClip(image_path)
        image_clip = self._with_duration(image_clip, scene_duration)
        image_clip = self._set_audio(image_clip, audio_clip)

        # 자막은 장면 이미지 위에 얇은 오버레이로 얹어서 가독성과 광고 느낌을 높임
        caption_clip = self._create_caption_clip(
            caption_text=str(scene.get("caption", "")),
            section_text=str(scene.get("section", "")),
            frame_size=image_clip.size,
            duration=scene_duration,
        )

        composed_clip = CompositeVideoClip([image_clip, caption_clip], size=image_clip.size)
        composed_clip = self._with_duration(composed_clip, scene_duration)
        composed_clip = self._set_audio(composed_clip, audio_clip)

        return composed_clip, [audio_clip, caption_clip]


    # 자막 이미지를 생성하는 메서드로, 장면의 캡션과 섹션 텍스트를 받아 프레임 하단에 오버레이로 그려 넣음
    def _create_caption_clip(
        self,
        caption_text: str,
        section_text: str,
        frame_size: tuple[int, int],
        duration: float,
    ):
        # 프레임 하단에 들어갈 자막 이미지를 직접 그려서, TextClip 의존성과 ImageMagick 문제를 피한다.
        frame_width, frame_height = frame_size
        overlay = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_size = max(32, frame_width // 24)
        font_path = self._find_font_path()
        if font_path:
            try:
                font = ImageFont.truetype(font_path, font_size)
                small_font = ImageFont.truetype(font_path, max(22, font_size - 10))
            except OSError:
                font = ImageFont.load_default()
                small_font = ImageFont.load_default()
        else:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        text = caption_text.strip()
        if not text:
            text = ""

        max_text_width = int(frame_width * 0.82)
        wrapped_lines = self._wrap_text(draw, text, font, max_text_width)
        if not wrapped_lines:
            wrapped_lines = [""]

        line_spacing = max(8, font_size // 4)
        text_heights = []
        text_widths = []
        for line in wrapped_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_widths.append(bbox[2] - bbox[0])
            text_heights.append(bbox[3] - bbox[1])

        block_width = min(max(text_widths) if text_widths else max_text_width, max_text_width)
        block_height = sum(text_heights) + line_spacing * (len(wrapped_lines) - 1)

        padding_x = 42
        padding_y = 28
        box_width = block_width + padding_x * 2
        box_height = block_height + padding_y * 2 + 34

        box_x = max(24, (frame_width - box_width) // 2)
        box_y = frame_height - box_height - max(36, frame_height // 18)
        box_rect = [box_x, box_y, box_x + box_width, box_y + box_height]

        self._draw_rounded_rectangle(draw, box_rect, radius=28, fill=(0, 0, 0, 168))

        badge_text = section_text
        badge_bbox = draw.textbbox((0, 0), badge_text, font=small_font)
        badge_width = badge_bbox[2] - badge_bbox[0]
        badge_height = badge_bbox[3] - badge_bbox[1]
        badge_padding_x = 18
        badge_padding_y = 8
        badge_rect = [
            box_x + padding_x,
            box_y + 16,
            box_x + padding_x + badge_width + badge_padding_x * 2,
            box_y + 16 + badge_height + badge_padding_y * 2,
        ]
        self._draw_rounded_rectangle(draw, badge_rect, radius=18, fill=(255, 255, 255, 36))
        draw.text(
            (badge_rect[0] + badge_padding_x, badge_rect[1] + badge_padding_y),
            badge_text,
            fill=(255, 255, 255, 245),
            font=small_font,
        )

        text_start_y = badge_rect[3] + 16
        current_y = text_start_y
        for line in wrapped_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            line_x = box_x + (box_width - line_width) // 2
            shadow_offset = 2
            draw.text((line_x + shadow_offset, current_y + shadow_offset), line, fill=(0, 0, 0, 160), font=font)
            draw.text((line_x, current_y), line, fill=(255, 255, 255, 255), font=font)
            current_y += line_height + line_spacing

        caption_clip = ImageClip(np.array(overlay))
        return self._with_duration(caption_clip, duration)


    # 장면의 이미지 경로를 확인하고, 로컬 파일이면 그대로 사용하고, URL이면 임시 캐시 폴더에 다운로드하여 반환
    def _resolve_image_path(self, asset_name: str) -> str | None:
        if not asset_name:
            return None

        if asset_name.startswith("http://") or asset_name.startswith("https://"):
            cache_dir = os.path.join(self.assets_dir, "downloaded")
            ensure_directories(cache_dir)
            parsed_url = urlparse(asset_name)
            filename = os.path.basename(parsed_url.path) or "downloaded_image"
            file_root, file_ext = os.path.splitext(filename)
            if not file_ext:
                file_ext = ".jpg"
            cache_name = hashlib.sha1(asset_name.encode("utf-8")).hexdigest()
            cached_path = os.path.join(cache_dir, f"{cache_name}{file_ext}")
            if os.path.exists(cached_path):
                return cached_path

            try:
                with urlopen(asset_name, timeout=20) as response, open(cached_path, "wb") as file_handle:
                    file_handle.write(response.read())
                print(f"[ProducerAgent] Downloaded asset: {asset_name} -> {cached_path}")
                return cached_path
            except OSError as exc:
                print(f"[ProducerAgent] Failed to download asset: {asset_name} -> {exc}")
                return None

        local_path = os.path.join(self.assets_dir, asset_name)
        if os.path.exists(local_path):
            return local_path

        return None


    # MoviePy 클립을 닫아 파일 핸들을 해제하는 메서드
    def _wrap_text(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        if not text:
            return []

        wrapped_lines: list[str] = []
        for paragraph in text.splitlines():
            if not paragraph.strip():
                wrapped_lines.append("")
                continue

            current_line = ""
            for word in paragraph.split(" "):
                candidate_line = word if not current_line else f"{current_line} {word}"
                bbox = draw.textbbox((0, 0), candidate_line, font=font)
                if bbox[2] - bbox[0] <= max_width:
                    current_line = candidate_line
                    continue

                if current_line:
                    wrapped_lines.append(current_line)
                current_line = word

                # 한국어처럼 공백이 적은 문장은 글자 단위로 추가 분해
                if draw.textbbox((0, 0), current_line, font=font)[2] - draw.textbbox((0, 0), current_line, font=font)[0] > max_width:
                    char_line = ""
                    for character in word:
                        candidate_char_line = char_line + character
                        char_bbox = draw.textbbox((0, 0), candidate_char_line, font=font)
                        if char_bbox[2] - char_bbox[0] <= max_width:
                            char_line = candidate_char_line
                            continue
                        if char_line:
                            wrapped_lines.append(char_line)
                        char_line = character
                    current_line = char_line

            if current_line:
                wrapped_lines.append(current_line)

        return wrapped_lines


    # 둥근 사각형을 그리는 메서드
    def _draw_rounded_rectangle(self, draw: ImageDraw.ImageDraw, rect: list[int], radius: int, fill) -> None:
        # Pillow 버전에 따라 rounded_rectangle 지원 여부가 갈릴 수 있어 안전하게 처리한다.
        if hasattr(draw, "rounded_rectangle"):
            draw.rounded_rectangle(rect, radius=radius, fill=fill)
            return
        draw.rectangle(rect, fill=fill)


    # 번호가 붙은 파일명을 생성하는 메서드
    def _build_numbered_filename(self, base_filename: str) -> str:
        base_name, extension = os.path.splitext(base_filename)
        pattern = re.compile(rf"^{re.escape(base_name)}_(\d{{3}}){re.escape(extension)}$")

        existing_numbers: list[int] = []
        for file_name in os.listdir(self.video_dir):
            match = pattern.match(file_name)
            if match:
                existing_numbers.append(int(match.group(1)))

        next_number = (max(existing_numbers) + 1) if existing_numbers else 1
        return f"{base_name}_{next_number:03d}{extension}"


    # 음성 파일을 생성하는 메서드
    def _generate_audio(self, tts_text: str, scene_number: int) -> str:
        # 장면 번호를 파일명에 넣어 나중에 문제 장면을 추적하기 쉽게 만든다.
        audio_path = os.path.join(self.audio_dir, f"audio_{scene_number}.mp3")
        return self.tts_provider.generate_audio(tts_text, audio_path)


    # 스토리보드의 분위기에 맞는 BGM 경로를 결정하는 메서드로, 외부 API를 사용하거나 로컬 라이브러리에서 선택
    def _resolve_bgm_path(self, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        return self.music_provider.resolve_bgm_path(self, storyboard, duration_seconds)


    # 외부 음악 생성 API를 호출하여 스토리보드의 분위기에 맞는 BGM을 생성하는 메서드로, API 응답에서 직접 오디오 파일을 받거나 URL 또는 Base64 인코딩된 오디오 데이터를 처리하여 파일로 저장
    def _generate_music_with_external_api(self, storyboard: dict[str, Any], duration_seconds: float) -> str | None:
        if not settings.music_api_url:
            return None
        if not settings.music_api_key:
            raise RuntimeError("MUSIC_API_KEY, SUDO_API_KEY, or SUNO_API_KEY is not configured.")

        mood = str(storyboard.get("video_metadata", {}).get("bgm_mood", "modern upbeat corporate"))
        concept = str(storyboard.get("video_metadata", {}).get("concept", "company promotional video"))
        prompt = f"{concept}. Instrumental background music, {mood}, clean corporate advertising style, no vocals."
        output_path = os.path.join(self.audio_dir, "generated_bgm.mp3")
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
            import base64

            with open(output_path, "wb") as file_handle:
                file_handle.write(base64.b64decode(str(audio_base64)))
            return output_path

        return None


    # VEO API를 사용하여 비디오를 렌더링하는 메서드
    def _render_video_with_veo(self, storyboard: dict[str, Any], output_filename: str) -> str:
        if not settings.veo_api_key:
            raise RuntimeError("VEO_API_KEY or GEMINI_API_KEY is not configured.")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is required for VIDEO_PROVIDER=veo. Install requirements.txt.") from exc

        output_filename = self._build_numbered_filename(output_filename)
        output_video_path = os.path.join(self.video_dir, output_filename)
        prompt = self._build_veo_prompt(storyboard)
        client = genai.Client(api_key=settings.veo_api_key)
        config_kwargs = {
            "number_of_videos": 1,
            "aspect_ratio": settings.veo_aspect_ratio,
            "resolution": settings.veo_resolution,
            "duration_seconds": settings.veo_duration_seconds,
        }
        config = types.GenerateVideosConfig(**config_kwargs)
        operation = client.models.generate_videos(
            model=settings.veo_model,
            prompt=prompt,
            config=config,
        )

        started_at = time.monotonic()
        while not operation.done:
            if time.monotonic() - started_at > settings.veo_timeout_seconds:
                raise RuntimeError("Veo video generation timed out.")
            print("[ProducerAgent] Waiting for Veo video generation to complete...")
            time.sleep(settings.veo_poll_interval_seconds)
            operation = client.operations.get(operation)

        video = operation.response.generated_videos[0].video
        client.files.download(file=video)
        video.save(output_video_path)
        return output_video_path


    # VEO API에 전달할 프롬프트를 스토리보드에서 구성하는 메서드로,
    # 스토리보드의 메타데이터와 장면 정보를 바탕으로 영상의 콘셉트, 타겟, 스타일, 각 장면의 설명과 나레이션을 포함한 프롬프트 텍스트를 생성
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


    # URL에서 파일을 다운로드하는 메서드로, API 키가 필요한 경우 헤더에 포함하여 요청하고, 스트리밍으로 받아서 지정된 경로에 저장한다.
    def _download_file(self, url: str, output_path: str, api_key: str | None = None) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        with requests.get(url, headers=headers, stream=True, timeout=settings.request_timeout_seconds) as response:
            response.raise_for_status()
            with open(output_path, "wb") as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file_handle.write(chunk)


    # 여러 가능한 키에서 첫 번째로 존재하는 값을 반환하는 유틸리티 메서드로, API 응답에서 다양한 필드 이름으로 제공될 수 있는 오디오 URL이나 Base64 데이터를 안전하게 추출하기 위해 사용
    def _first_present(self, data: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            value = data.get(key)
            if value:
                return value
        return None


    # MoviePy 버전에 따라 duration 설정 메서드가 다를 수 있어 호환성을 유지하는 래퍼 메서드로, 클립의 지속 시간을 지정된 값으로 설정하여 장면의 길이를 나레이션에 맞춤
    def _with_duration(self, clip, duration: float):
        if hasattr(clip, "with_duration"):
            return clip.with_duration(duration)
        return clip.set_duration(duration)


    # MoviePy 버전에 따라 오디오 설정 메서드가 다를 수 있어 호환성을 유지하는 래퍼 메서드로, 클립에 오디오 트랙을 설정하여 장면에 나레이션과 BGM을 적용
    def _set_audio(self, clip, audio_clip):
        if hasattr(clip, "with_audio"):
            return clip.with_audio(audio_clip)
        return clip.set_audio(audio_clip)


    # 클립을 닫는 메서드로, 클립의 close 메서드를 호출하여 리소스를 해제
    def _close_clips(self, clips) -> None:
        # 닫기 실패는 전체 종료를 막지 않도록 조용히 무시
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
