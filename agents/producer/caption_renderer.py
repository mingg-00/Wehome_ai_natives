from __future__ import annotations            # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화

import os                                     # 파일 경로 처리를 위해 표준 라이브러리의 os 모듈을 사용

import numpy as np                            # 이미지 데이터를 배열로 처리하기 위해 NumPy를 사용
from moviepy import ImageClip                 # 이미지 클립 생성을 위해 MoviePy의 ImageClip을 사용
from PIL import Image, ImageDraw, ImageFont   # 이미지 렌더링을 위해 Pillow 라이브러리의 Image, ImageDraw, ImageFont 모듈을 사용


# 캡션을 이미지 클립으로 렌더링하는 클래스
class CaptionRenderer:
    
    # 캡션 텍스트와 섹션 텍스트를 받아 프레임 크기에 맞게 텍스트를 래핑하고, 배경과 섹션 배지를 포함한 이미지 클립을 생성하는 메서드로, 텍스트의 가독성을 높이기 위해 그림자 효과도 적용
    def create_caption_clip(
        self,
        caption_text: str,
        section_text: str,
        frame_size: tuple[int, int],
        duration: float,
    ):
        frame_width, frame_height = frame_size
        overlay = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_size = max(32, frame_width // 24)
        font_path = self.find_font_path()
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
        max_text_width = int(frame_width * 0.82)
        wrapped_lines = self.wrap_text(draw, text, font, max_text_width) or [""]

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

        self.draw_rounded_rectangle(draw, box_rect, radius=28, fill=(0, 0, 0, 168))

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
        self.draw_rounded_rectangle(draw, badge_rect, radius=18, fill=(255, 255, 255, 36))
        draw.text(
            (badge_rect[0] + badge_padding_x, badge_rect[1] + badge_padding_y),
            badge_text,
            fill=(255, 255, 255, 245),
            font=small_font,
        )

        current_y = badge_rect[3] + 16
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
        return self.with_duration(caption_clip, duration)

    # 시스템에서 사용할 수 있는 글꼴 경로를 찾아 반환하는 정적 메서드로, 여러 후보 경로를 확인하여 존재하는 첫 번째 경로를 반환하며, 글꼴이 없는 경우 None을 반환
    @staticmethod
    def find_font_path() -> str | None:
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

    # 텍스트를 주어진 최대 너비에 맞게 래핑하는 정적 메서드로, 단어 단위로 텍스트를 분할하여 각 줄이 최대 너비를 초과하지 않도록 래핑하며, 단어가 너무 길면 문자 단위로도 래핑하여 긴 단어도 처리할 수 있도록 함
    @staticmethod
    def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
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

                current_bbox = draw.textbbox((0, 0), current_line, font=font)
                if current_bbox[2] - current_bbox[0] > max_width:
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

    # 주어진 사각형 영역에 반경이 있는 모서리를 가진 사각형을 그리는 정적 메서드로, ImageDraw 객체가 rounded_rectangle 메서드를 지원하는 경우 이를 사용하여 그리며, 지원하지 않는 경우 일반 사각형으로 대체하여 그리는 방식으로 구현
    @staticmethod
    def draw_rounded_rectangle(draw: ImageDraw.ImageDraw, rect: list[int], radius: int, fill) -> None:
        if hasattr(draw, "rounded_rectangle"):
            draw.rounded_rectangle(rect, radius=radius, fill=fill)
            return
        draw.rectangle(rect, fill=fill)

    @staticmethod
    def with_duration(clip, duration: float):
        return clip.with_duration(duration)
