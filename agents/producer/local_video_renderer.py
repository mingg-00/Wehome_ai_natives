from __future__ import annotations                        # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화

import os                                                 # 파일 경로 처리를 위해 표준 라이브러리의 os 모듈을 사용
from typing import Any                                    # Any 타입을 사용하여 스토리보드의 구조를 유연하게 처리

import numpy as np                                        # 이미지 데이터를 배열로 처리하기 위해 NumPy를 사용
from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips # MoviePy의 다양한 클립과 편집 기능을 사용하기 위해 필요한 모듈을 가져옴
from moviepy.audio.AudioClip import CompositeAudioClip    # 오디오 클립을 합성하기 위해 MoviePy의 CompositeAudioClip을 사용                       
from PIL import Image, ImageOps                           # 이미지 처리를 위해 Pillow 라이브러리의 Image와 ImageOps 모듈을 사용

from config.settings import settings                      # 애플리케이션 설정을 가져오기 위해 config.settings 모듈에서 settings 객체를 가져옴


# 로컬 파일 시스템에서 비디오를 렌더링하는 클래스
class LocalVideoRenderer:

    # 스토리보드와 출력 파일 이름을 받아 비디오를 렌더링하는 메인 메서드
    # 각 씬을 렌더링하여 최종 비디오를 생성하며, 렌더링된 클립과 리소스를 적절히 닫아 리소스 누수를 방지
    def render_video(self, agent: Any, storyboard: dict[str, Any], output_filename: str) -> str:
        scenes = storyboard.get("scenes", [])
        if not scenes:
            raise RuntimeError("스토리보드에 장면이 없습니다.")

        rendered_clips = []
        clip_resources = []
        final_video = None
        final_audio = None
        bgm_clip = None
        bgm_mixed_clip = None

        try:
            for scene in scenes:
                scene_clip, clip_resources_for_scene = self.render_scene(agent, scene)
                if scene_clip is None:
                    continue
                rendered_clips.append(scene_clip)
                clip_resources.extend(clip_resources_for_scene)

            if not rendered_clips:
                raise RuntimeError("렌더링할 수 있는 장면을 만들지 못했습니다.")

            final_video = concatenate_videoclips(rendered_clips, method="compose")
            bgm_path = agent.resolve_bgm_path(storyboard, float(final_video.duration))
            if bgm_path:
                print(f"[ProducerAgent] 선택된 BGM: {bgm_path}")
                bgm_clip = AudioFileClip(bgm_path)
                bgm_mixed_clip = self.subclipped(
                    bgm_clip,
                    0,
                    min(float(bgm_clip.duration), float(final_video.duration)),
                )
                bgm_mixed_clip = self.with_volume_scaled(bgm_mixed_clip, agent.bgm_volume)

                if final_video.audio is not None:
                    final_audio = CompositeAudioClip([final_video.audio, bgm_mixed_clip])
                else:
                    final_audio = bgm_mixed_clip
                final_video = self.with_audio(final_video, final_audio)

            output_filename = agent.build_numbered_filename(output_filename)
            output_video_path = os.path.join(agent.video_dir, output_filename)
            final_video.write_videofile(
                output_video_path,
                fps=24,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=os.path.join(agent.audio_dir, agent.build_temp_audio_filename()),
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
            return output_video_path
        finally:
            self.close_clips([clip for clip in [final_video, final_audio] if clip is not None])
            self.close_clips(rendered_clips)
            self.close_clips(clip_resources)
            self.close_clips([clip for clip in [bgm_mixed_clip, bgm_clip] if clip is not None])


    # 각 씬을 렌더링하는 메서드
    # 씬에 매칭된 자산을 로드하여 이미지 클립을 생성하고, TTS 텍스트를 오디오 클립으로 변환하여 이미지 클립과 합성한 후, 캡션 클립과 함께 최종 씬 클립을 생성하여 반환
    def render_scene(self, agent: Any, scene: dict[str, Any]):
        asset_name = scene.get("matched_asset", "")
        image_path = agent.asset_resolver.resolve_image_path(asset_name)
        if image_path is None:
            print(f"[ProducerAgent] 자산을 찾을 수 없어 장면 {scene.get('scene_number')}을 건너뜁니다: {asset_name}")
            return None, []

        tts_text = scene.get("tts_script", "")
        if not tts_text:
            print(f"[ProducerAgent] TTS 문구가 비어 있어 장면 {scene.get('scene_number')}을 건너뜁니다.")
            return None, []

        audio_path = agent.generate_audio(tts_text, int(scene["scene_number"]))
        audio_clip = AudioFileClip(audio_path)
        scene_duration = max(float(audio_clip.duration), 0.1)

        try:
            image_clip = self.create_scene_image_clip(agent.frame_size, image_path, scene, scene_duration)
        except OSError as exc:
            print(f"[ProducerAgent] 이미지 준비 실패로 장면 {scene.get('scene_number')}을 건너뜁니다: {exc}")
            audio_clip.close()
            return None, []
        image_clip = self.with_audio(image_clip, audio_clip)

        caption_clip = agent.caption_renderer.create_caption_clip(
            caption_text=str(scene.get("caption", "")),
            section_text=str(scene.get("section", "")),
            frame_size=agent.frame_size,
            duration=scene_duration,
        )

        composed_clip = CompositeVideoClip([image_clip, caption_clip], size=agent.frame_size)
        composed_clip = self.with_duration(composed_clip, scene_duration)
        composed_clip = self.with_audio(composed_clip, audio_clip)

        return composed_clip, [audio_clip, caption_clip]


    # 씬의 이미지 클립을 생성하는 메서드
    # 자산 이미지를 로드하여 프레임 크기에 맞게 크롭 및 리사이즈한 후, 카메라 효과를 적용하여 최종 이미지 클립을 생성하여 반환
    def create_scene_image_clip(
        self,
        frame_size: tuple[int, int],
        image_path: str,
        scene: dict[str, Any],
        duration: float,
    ):
        frame_image = self.load_cover_frame(image_path, frame_size)
        image_clip = ImageClip(np.array(frame_image))
        image_clip = self.with_duration(image_clip, duration)
        image_clip = self.apply_camera_effect(frame_size, image_clip, str(scene.get("camera_effect", "")), duration)
        return image_clip


    # 씬의 자산 이미지를 로드하여 프레임 크기에 맞게 크롭 및 리사이즈하는 메서드
    # 이미지의 가로세로 비율을 프레임에 맞게 조정하기 위해 중앙에서 크롭한 후, 프레임 크기에 맞게 리사이즈하여 반환
    def load_cover_frame(self, image_path: str, frame_size: tuple[int, int]) -> Image.Image:
        frame_width, frame_height = frame_size
        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            source_width, source_height = image.size
            if source_width <= 0 or source_height <= 0:
                raise OSError("이미지 크기가 올바르지 않습니다.")

            target_ratio = frame_width / frame_height
            source_ratio = source_width / source_height

            if source_ratio > target_ratio:
                crop_width = int(source_height * target_ratio)
                crop_left = max(0, (source_width - crop_width) // 2)
                crop_box = (crop_left, 0, crop_left + crop_width, source_height)
            else:
                crop_height = int(source_width / target_ratio)
                crop_top = max(0, (source_height - crop_height) // 2)
                crop_box = (0, crop_top, source_width, crop_top + crop_height)

            image = image.crop(crop_box)
            return image.resize(frame_size, self.image_resize_filter())


    # 씬에 카메라 효과를 적용하는 메서드
    # 설정된 카메라 효과에 따라 이미지 클립에 패닝, 줌인/줌아웃, 페이드 효과를 적용하여 최종 클립을 반환
    def apply_camera_effect(self, frame_size: tuple[int, int], clip, camera_effect: str, duration: float):
        if not settings.local_video_motion_enabled:
            return self.with_position(clip, ("center", "center"))

        effect = camera_effect.lower()
        frame_width, frame_height = frame_size

        if "pan" in effect:
            scale = 1.08
            clip = self.resized(clip, scale)
            extra_width = frame_width * scale - frame_width
            extra_height = frame_height * scale - frame_height

            def pan_position(t):
                progress = self.motion_progress(t, duration)
                if "up" in effect:
                    return (-extra_width / 2, -extra_height * progress)
                if "down" in effect:
                    return (-extra_width / 2, -extra_height * (1 - progress))
                if "right" in effect:
                    return (-extra_width * (1 - progress), -extra_height / 2)
                return (-extra_width * progress, -extra_height / 2)

            return self.with_position(clip, pan_position)

        zoom_start, zoom_end = (1.06, 1.0) if "out" in effect else (1.0, 1.08)
        if "fade" in effect:
            zoom_start, zoom_end = 1.0, 1.03

        def zoom_scale(t):
            progress = self.motion_progress(t, duration)
            return zoom_start + (zoom_end - zoom_start) * progress

        def zoom_position(t):
            scale = zoom_scale(t)
            return (
                (frame_width - frame_width * scale) / 2,
                (frame_height - frame_height * scale) / 2,
            )

        clip = self.resized(clip, zoom_scale)
        return self.with_position(clip, zoom_position)


    
    # 주어진 시간과 지속 시간을 기반으로 모션 효과의 진행 정도를 계산하는 정적 메서드
    # 지속 시간이 0 이하인 경우 1.0을 반환하며, 그렇지 않은 경우 현재 시간에 대한 진행 정도를 0.0에서 1.0 사이의 값으로 반환
    @staticmethod
    def motion_progress(t: float, duration: float) -> float:
        if duration <= 0:
            return 1.0
        return max(0.0, min(1.0, float(t) / float(duration)))


    # 이미지 리사이즈에 사용할 필터를 반환하는 정적 메서드로, Pillow 라이브러리의 버전에 따라 적절한 리사이즈 필터를 선택하여 반환
    @staticmethod
    def image_resize_filter():
        if hasattr(Image, "Resampling"):
            return Image.Resampling.LANCZOS
        return Image.LANCZOS


    @staticmethod
    def with_duration(clip, duration: float):
        return clip.with_duration(duration)

    @staticmethod
    def with_audio(clip, audio_clip):
        return clip.with_audio(audio_clip)
    
    @staticmethod
    def resized(clip, size_or_scale):
        return clip.resized(size_or_scale)

    # with_position 메서드로, 클립의 위치를 지정된 위치로 설정하는 정적 메서드
    @staticmethod
    def with_position(clip, position):
        return clip.with_position(position)

    # 클립을 주어진 시작 시간과 종료 시간으로 자르는 정적 메서드
    # 클립이 subclipped 메서드를 지원하는 경우 이를 사용하여 자르며, 지원하지 않는 경우 클립의 subclip 메서드를 사용하여 자름
    @staticmethod
    def subclipped(clip, start_time: float, end_time: float):
        return clip.subclipped(start_time, end_time)

    # 볼륨이 조정된 오디오 클립을 반환하는 정적 메서드
    # 오디오 클립이 with_volume_scaled 메서드를 지원하는 경우 이를 사용하여 볼륨을 조정하며, 지원하지 않는 경우 볼륨을 조정하는 다른 방법을 적용하여 반환
    @staticmethod
    def with_volume_scaled(clip, volume: float):
        return clip.with_volume_scaled(volume)

    # 클립을 닫는 정적 메서드
    # 클립이 with_duration, with_audio, resized, with_position, subclipped, with_volume_scaled 등의 메서드를 지원하는 경우 이를 사용하여 클립을 닫으며, 지원하지 않는 경우 close 메서드를 호출하여 클립을 닫음
    @staticmethod
    def close_clips(clips) -> None:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
