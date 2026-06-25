"""위홈 카드뉴스 자동 생성 모듈.

LLM으로 슬라이드 구성 생성 → Pillow로 1080×1080 PNG 렌더링.
generate(topic) → List[Path]  (슬라이드 이미지 파일 경로 목록)
"""
from __future__ import annotations

import json
import math
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from . import llm
from . import rag

# ── 브랜드 ──────────────────────────────────────────────────────────────
BRAND_PURPLE = (104, 0, 205)       # #6800CD
BRAND_PURPLE_LIGHT = (237, 220, 255)  # 연보라 배경용
WHITE = (255, 255, 255)
GRAY_TEXT = (80, 80, 100)
DARK_TEXT = (20, 10, 40)

SIZE = (1080, 1080)

_ASSET_DIR = Path(__file__).parent.parent / "assets"
_ICON_PATH = _ASSET_DIR / "wehome_icon.png"

# 출력 폴더
_OUT_DIR = Path(__file__).parent.parent / "output" / "card_news"

# ── 폰트 ────────────────────────────────────────────────────────────────
_FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    idx = 3 if bold else 2  # AppleSDGothicNeo Bold / Regular index
    try:
        return ImageFont.truetype(_FONT_PATH, size, index=idx)
    except Exception:
        return ImageFont.load_default()


# ── LLM 슬라이드 구성 생성 ──────────────────────────────────────────────
_SLIDE_PROMPT = """
위홈(wehome) SNS 카드뉴스 슬라이드를 JSON으로 작성하세요.
위홈은 한국 정부가 유일하게 인증한 공유숙박 플랫폼입니다.

주제: {topic}

규칙:
- slides 배열: 표지 1장 + 내용 3~4장 + CTA 1장 (총 5~6장)
- 각 슬라이드: type("cover"|"content"|"cta"), title(20자 이내), body(60자 이내, content만)
- cover: title만 (subtitle 선택)
- cta: title + cta_text("지금 위홈에서 시작하세요" 등)
- 한국어, 간결하게

JSON만 반환:
{{"slides": [...]}}
"""

def _generate_slides(topic: str) -> list[dict]:
    knowledge = rag.retrieve_as_context(topic, top_k=3)
    prompt = _SLIDE_PROMPT.format(topic=topic)
    if knowledge:
        prompt = knowledge + "\n\n위 자료를 참고해서 아래 요청을 수행하세요.\n\n" + prompt
    data = llm.chat_json("당신은 한국 공유숙박 플랫폼 위홈의 SNS 마케터입니다.", prompt)
    if data and "slides" in data:
        return data["slides"]
    # 폴백: 기본 구성
    return [
        {"type": "cover", "title": topic, "subtitle": "위홈이 알려드립니다"},
        {"type": "content", "title": "핵심 포인트 1", "body": "위홈은 한국 정부 공인 공유숙박 플랫폼입니다."},
        {"type": "content", "title": "핵심 포인트 2", "body": "2,300개 이상의 검증된 숙소를 제공합니다."},
        {"type": "content", "title": "핵심 포인트 3", "body": "안전하고 합법적인 공유숙박을 경험하세요."},
        {"type": "cta", "title": "지금 시작하세요", "cta_text": "wehome.me 에서 예약하기"},
    ]


# ── 공통 드로잉 유틸 ────────────────────────────────────────────────────
def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def _draw_text_wrapped(draw: ImageDraw.ImageDraw, text: str, font, fill,
                       x: int, y: int, max_width: int) -> int:
    """자동 줄바꿈 텍스트 그리기. 마지막 y 좌표 반환."""
    avg_char = font.size * 0.6
    chars_per_line = max(1, int(max_width / avg_char))
    lines = textwrap.wrap(text, width=chars_per_line)
    line_h = font.size + 8
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def _paste_icon(img: Image.Image, size: int = 80, pos: tuple = (60, 60),
                white_version: bool = False):
    """위홈 아이콘을 이미지에 합성."""
    if not _ICON_PATH.exists():
        return
    icon = Image.open(_ICON_PATH).convert("RGBA").resize((size, size), Image.LANCZOS)
    if white_version:
        # 흰색 배경 위에 아이콘을 그대로 사용 (이미 퍼플)
        pass
    img.paste(icon, pos, icon if icon.mode == "RGBA" else None)


# ── 슬라이드 렌더러 ─────────────────────────────────────────────────────
def _render_cover(slide: dict, idx: int) -> Image.Image:
    img = Image.new("RGB", SIZE, BRAND_PURPLE)
    draw = ImageDraw.Draw(img)

    # 배경 장식 원
    draw.ellipse([700, -200, 1300, 400], fill=(130, 30, 230))
    draw.ellipse([-200, 700, 300, 1200], fill=(80, 0, 170))

    # 아이콘 (흰색 배경 없이 그대로)
    _paste_icon(img, size=120, pos=(60, 60))

    # 슬라이드 번호
    draw.text((SIZE[0] - 80, 60), f"01", font=_font(36, bold=True), fill=(255, 255, 255, 180))

    # 제목
    title = slide.get("title", "위홈")
    title_font = _font(72, bold=True)
    _draw_text_wrapped(draw, title, title_font, WHITE, 80, 420, 900)

    # 서브타이틀
    sub = slide.get("subtitle", "")
    if sub:
        sub_font = _font(38)
        _draw_text_wrapped(draw, sub, sub_font, (220, 200, 255), 80, 580, 900)

    # 하단 위홈 워드마크
    draw.text((80, SIZE[1] - 100), "wehome", font=_font(44, bold=True), fill=(220, 200, 255))
    draw.text((80, SIZE[1] - 55), "welcome home!", font=_font(26), fill=(180, 150, 230))

    return img


def _render_content(slide: dict, idx: int, total: int) -> Image.Image:
    img = Image.new("RGB", SIZE, WHITE)
    draw = ImageDraw.Draw(img)

    # 상단 퍼플 배너
    draw.rectangle([0, 0, SIZE[0], 180], fill=BRAND_PURPLE)

    # 아이콘 (상단 배너 위)
    _paste_icon(img, size=80, pos=(60, 50))

    # 슬라이드 번호 (상단 우측)
    num_str = f"{idx:02d} / {total - 1:02d}"
    draw.text((SIZE[0] - 160, 65), num_str, font=_font(32, bold=True), fill=(220, 200, 255))

    # 제목 (배너 위)
    title = slide.get("title", "")
    draw.text((80, 210), title, font=_font(58, bold=True), fill=DARK_TEXT)

    # 구분선 (퍼플)
    draw.rectangle([80, 300, 200, 308], fill=BRAND_PURPLE)

    # 본문
    body = slide.get("body", "")
    body_font = _font(42)
    _draw_text_wrapped(draw, body, body_font, GRAY_TEXT, 80, 340, 920)

    # 하단 브랜드 바
    draw.rectangle([0, SIZE[1] - 80, SIZE[0], SIZE[1]], fill=BRAND_PURPLE_LIGHT)
    draw.text((80, SIZE[1] - 56), "wehome  |  welcome home!",
              font=_font(28), fill=BRAND_PURPLE)

    return img


def _render_cta(slide: dict, idx: int) -> Image.Image:
    img = Image.new("RGB", SIZE, BRAND_PURPLE)
    draw = ImageDraw.Draw(img)

    # 배경 장식
    draw.ellipse([600, 600, 1300, 1300], fill=(130, 30, 230))

    # 아이콘
    _paste_icon(img, size=100, pos=(60, 60))

    # 제목
    title = slide.get("title", "지금 시작하세요")
    title_font = _font(68, bold=True)
    _draw_text_wrapped(draw, title, title_font, WHITE, 80, 380, 920)

    # CTA 버튼 형태
    cta_text = slide.get("cta_text", "wehome.me 에서 예약하기")
    _draw_rounded_rect(draw, [80, 580, 920, 670], radius=40, fill=WHITE)
    draw.text((100, 600), cta_text, font=_font(36, bold=True), fill=BRAND_PURPLE)

    # 하단
    draw.text((80, SIZE[1] - 100), "wehome.me", font=_font(40, bold=True), fill=(220, 200, 255))

    return img


# ── 메인 API ────────────────────────────────────────────────────────────
def generate(topic: str, out_dir: Optional[Path] = None) -> list[Path]:
    """주제를 받아 카드뉴스 슬라이드 PNG 파일 목록 반환."""
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    save_dir = out_dir or _OUT_DIR

    slides = _generate_slides(topic)
    total = len(slides)
    paths: list[Path] = []

    safe_topic = "".join(c for c in topic[:20] if c.isalnum() or c in " _-").strip().replace(" ", "_")
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{ts}_{safe_topic}"

    for i, slide in enumerate(slides):
        stype = slide.get("type", "content")
        if stype == "cover":
            img = _render_cover(slide, i)
        elif stype == "cta":
            img = _render_cta(slide, i)
        else:
            img = _render_content(slide, i + 1, total)

        path = save_dir / f"{prefix}_{i + 1:02d}.png"
        img.save(path, "PNG", quality=95)
        paths.append(path)

    return paths
