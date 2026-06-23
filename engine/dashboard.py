"""시각 대시보드 — 이전 구조 복원 + 위홈 바이올렛 색상.

게시자 화면: 본문만 노출(메타·schema 숨김, 파일엔 보존).
'새 SNS 글 생성' 폼 유지 + SNS 큐 + 생성된 콘텐츠. 액센트 색은 위홈 #7c3aed.
served by server.py (http://127.0.0.1:8765).
"""
from __future__ import annotations

import json

import markdown as md

from .config import OUTPUT_DIR
from . import publisher, social, schedule as sched, events as evt

# ---------------------------------------------------------------------------
# SVG 아이콘 시스템 (Lucide 라인 아이콘) — 이모지 대체
# ---------------------------------------------------------------------------
_ICON_PATHS = {
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "calendar-clock": '<path d="M21 7.5V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6"/><path d="M16 2v4M8 2v4M3 10h7"/><circle cx="18" cy="16" r="4"/><path d="M18 14.5V16l1 1"/>',
    "smartphone": '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/>',
    "sparkles": '<path d="M12 3l1.9 4.8L18.5 9l-4.6 1.2L12 15l-1.9-4.8L5.5 9l4.6-1.2z"/><path d="M19 14l.7 1.8L21.5 17l-1.8.7L19 19.5l-.7-1.8L16.5 17l1.8-.5z"/>',
    "file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
    "trending-up": '<path d="M22 7l-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
    "home": '<path d="M3 9.5L12 3l9 6.5V21a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
    "send": '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/>',
}


def _icon(name: str, size: int = 18, color: str = "currentColor", stroke: float = 2) -> str:
    """Lucide 스타일 인라인 SVG 아이콘 반환."""
    path = _ICON_PATHS.get(name, "")
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round" style="vertical-align:-3px;flex-shrink:0">{path}</svg>'
    )


# 브랜드 글리프 (네비용) — 단색 fill SVG
_BRAND_PATHS = {
    "instagram": '<rect x="2.5" y="2.5" width="19" height="19" rx="5.5"/><circle cx="12" cy="12" r="4.2"/><circle cx="17.6" cy="6.4" r="1.2"/>',
    "threads": '<path d="M16.3 11.4c-.1 0-.2-.1-.3-.1-.2-3-1.8-4.7-4.5-4.7-1.6 0-3 .7-3.8 2l1.5 1c.6-.9 1.5-1.1 2.3-1.1 1.5 0 2.3.9 2.4 2.3-.6-.1-1.2-.2-1.9-.2-2.4 0-4 1.3-3.9 3.2.1 1.6 1.5 2.6 3.2 2.6 1.4 0 2.9-.7 3.4-2.7.3.7.9 1.2 1.6 1.5-.5-1.3-.3-3.3 0-3.9zm-4.6 2.9c-.6 0-1.3-.3-1.4-.9-.1-.7.7-1 1.6-1 .5 0 1 .1 1.5.2-.2 1.2-.9 1.7-1.7 1.7z"/>',
    "facebook": '<path d="M22 12a10 10 0 1 0-11.6 9.9v-7H7.9V12h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.5h-1.3c-1.2 0-1.6.8-1.6 1.6V12h2.8l-.4 2.9h-2.3v7A10 10 0 0 0 22 12z"/>',
    "youtube": '<path d="M21.6 7.2s-.2-1.4-.8-2c-.8-.8-1.6-.8-2-.9C15.9 4 12 4 12 4s-3.9 0-6.8.3c-.4 0-1.2.1-2 .9-.6.6-.8 2-.8 2S2 8.8 2 10.5v1.4c0 1.6.2 3.3.2 3.3s.2 1.4.8 2c.8.8 1.8.8 2.3.9 1.7.2 6.7.3 6.7.3s3.9 0 6.8-.3c.4 0 1.2-.1 2-.9.6-.6.8-2 .8-2s.2-1.6.2-3.3v-1.4c0-1.7-.2-3.3-.2-3.3zM9.9 14.6V8.9l5.2 2.9-5.2 2.8z"/>',
}


def _brand(name: str, size: int = 17) -> str:
    """SNS 브랜드 글리프 (흰색 단색)."""
    path = _BRAND_PATHS.get(name, "")
    fill = "none" if name == "instagram" else "#fff"
    stroke = "#fff" if name == "instagram" else "none"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )


_BADGE = {
    "APPROVED": ("#15803d", "#eafaf0"),
    "DRAFT": ("#6d5c00", "#f5eed6"),
    "PASS": ("#15803d", "#eafaf0"),
    "WARN": ("#7a5f00", "#f7efc5"),
    "FAIL": ("#a8253a", "#fbe9ec"),
}


def _badge(text: str) -> str:
    fg, bg = _BADGE.get(text, ("#5b21b6", "#ede9fe"))
    return (f'<span style="background:{bg};color:{fg};padding:3px 10px;'
            f'border-radius:var(--r-pill);font-size:11px;font-weight:600;'
            f'letter-spacing:.02em">{text}</span>')


def _publisher_view(text: str) -> tuple[str, bool]:
    """게시자 화면용: 본문(2번)만. 1)메타·3·4)schema는 숨김(파일엔 보존)."""
    start = text.find("## 2)")
    end = text.find("\n## 3)")
    if start != -1:
        body = text[start:end] if end != -1 else text[start:]
        nl = body.find("\n")
        return (body[nl + 1:].strip() if nl != -1 else body.strip()), True
    return (text[:end].rstrip() if end != -1 else text.rstrip()), (end != -1)


_GEN_FORM = f"""
  <div class="gen-form">
    <div class="gen-form-title">{_icon('sparkles', 16)} 새 SNS 글 생성 — 주제 입력 후 플랫폼 선택</div>
    <input id="genTopic" placeholder="예: K-pop concert stay in Korea / 합법 숙박 꿀팁" class="gen-input">
    <div class="gen-btn-row">
      <button class="gen-btn" onclick="gen('instagram',this)">Instagram</button>
      <button class="gen-btn" onclick="gen('threads',this)">Threads</button>
      <button class="gen-btn" onclick="gen('facebook',this)">Facebook</button>
      <button class="gen-btn gen-btn-primary" onclick="gen('all',this)">전체 생성</button>
    </div>
    <div class="gen-form-hint">선택한 플랫폼의 형식으로 AI가 자동 작성 → 아래 큐에 추가됩니다.</div>
  </div>"""


def _social_panel() -> str:
    q = social.queue()
    rows = []
    for it in q:
        st = _badge(it["status"])
        gov = _badge(it["governance"])
        if it["status"] == "POSTED":
            btn = f"<span class='posted-tag'>{_icon('check', 13)} 게시됨</span>"
        elif it["governance"] == "FAIL":
            btn = "<span style='color:#a8253a;font-weight:600'>검수 FAIL</span>"
        else:
            btn = (f"<button class='pub-btn' onclick=\"pub('{it['id']}', this)\">"
                   f"{_icon('send', 13)} 지금 게시</button>")
        rows.append(f"<tr><td>{_badge(it['platform'].upper())}</td><td>{st} {gov}</td>"
                    f"<td>{it['text'][:140]}</td><td style='white-space:nowrap'>{btn}</td></tr>")
    posted = sum(1 for it in q if it["status"] == "POSTED")
    appr = sum(1 for it in q if it["status"] == "APPROVED")
    empty_state = f"""
      <div class="empty-state">
        {_icon('send', 32, '#c4b5f9', 1.5)}
        <div class="empty-title">아직 생성된 게시물이 없습니다</div>
        <div class="empty-sub">위 입력칸에 주제를 적고 플랫폼을 누르면<br>AI가 자동으로 초안을 작성해 줍니다.</div>
      </div>"""
    table = (f"""<details open><summary>큐 보기 ({len(q)}건)</summary><div class="article"><table>
        <tr><th>플랫폼</th><th>상태/검수</th><th>문안</th><th>게시</th></tr>{''.join(rows)}
      </table></div></details>""" if q else empty_state)
    return f"""<div class="card">
      <div class="title">{_icon('smartphone', 19, '#7c3aed')} SNS 자동 포스팅 (자사 계정)</div>
      <div class="meta">총 {len(q)}건 · 승인 {appr} · 게시 {posted} · "지금 게시" = 승인+즉시 게시(토큰 없으면 dry-run)</div>
      {_GEN_FORM}
      {table}
    </div>"""


def _calendar_panel() -> str:
    """상단 위젯: 7일 캘린더 + 시즌 이벤트 + 언어 선택."""
    import datetime
    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(kst).date()
    days = [today + datetime.timedelta(days=i) for i in range(7)]
    day_labels = ["오늘", "내일"] + [
        (today + datetime.timedelta(days=i)).strftime("%-m/%-d") for i in range(2, 7)
    ]

    q = social.queue()
    by_date: dict[str, list[dict]] = {}
    unscheduled = []
    for it in q:
        if it["status"] == "POSTED":
            continue
        sa = it.get("scheduled_at")
        if not sa:
            unscheduled.append(it)
            continue
        try:
            t = datetime.datetime.fromisoformat(sa)
            if t.tzinfo is None:
                t = t.replace(tzinfo=kst)
            by_date.setdefault(t.astimezone(kst).date().isoformat(), []).append(it)
        except Exception:
            unscheduled.append(it)

    _PLAT_COLOR = {
        "instagram": "#dc2743", "threads": "#111", "facebook": "#1877f2",
        "x": "#000", "pinterest": "#e60023", "youtube": "#ff0000",
    }
    _STATUS_BG = {"APPROVED": "#e3f7e8", "DRAFT": "#fdf3d0"}

    # ── 7일 캘린더 컬럼 ────────────────────────────────────────────────
    cols = []
    for d, label in zip(days, day_labels):
        iso = d.isoformat()
        cells = []
        for it in by_date.get(iso, []):
            color = _PLAT_COLOR.get(it["platform"], "#7c3aed")
            bg = _STATUS_BG.get(it["status"], "#ede9fe")
            t_str = ""
            try:
                t = datetime.datetime.fromisoformat(it["scheduled_at"])
                if t.tzinfo is None:
                    t = t.replace(tzinfo=kst)
                t_str = t.astimezone(kst).strftime("%H:%M")
            except Exception:
                pass
            cells.append(
                f'<div style="background:{bg};border-left:3px solid {color};'
                f'border-radius:5px;padding:4px 7px;margin-bottom:4px;font-size:11px">'
                f'<b style="color:{color}">{it["platform"].upper()}</b> {t_str}'
                f'<div style="color:#555;margin-top:1px;white-space:nowrap;overflow:hidden;'
                f'text-overflow:ellipsis;max-width:120px">{it["text"][:38]}</div>'
                f'</div>'
            )
        empty = '<div style="color:#ddd;font-size:11px;text-align:center;padding:6px 0">—</div>'
        is_today = (iso == today.isoformat())
        cols.append(
            f'<td style="vertical-align:top;padding:7px 8px;min-width:110px;max-width:140px;'
            f'border-right:1px solid #f0eef8;{"background:#f8f5ff;" if is_today else ""}">'
            f'<div style="font-weight:700;font-size:12px;margin-bottom:3px;'
            f'color:{"#7c3aed" if is_today else "#5b21b6"}">{label}</div>'
            f'<div style="font-size:10px;color:#bbb;margin-bottom:5px">{iso}</div>'
            f'{"".join(cells) or empty}</td>'
        )

    # ── 시즌 이벤트 (3개 언어) ─────────────────────────────────────────
    upcoming = evt.upcoming_events(days_ahead=60)
    lang_event_html: dict[str, str] = {}
    for lang, name_key, topic_key, flag in [
        ("ko", "name_ko", "topic_ko", "🇰🇷"),
        ("en", "name_en", "topic_en", "🇺🇸"),
        ("ja", "name_en", "topic_ja", "🇯🇵"),
    ]:
        if not upcoming:
            lang_event_html[lang] = '<div style="color:#bbb;font-size:12px">예정 이벤트 없음</div>'
            continue
        items_html = []
        for ev in upcoming[:6]:
            d_str = f"D-{ev['days_until']}" if ev['days_until'] > 0 else "D-Day"
            name = ev.get(name_key, ev["name_ko"])
            topic = ev.get(topic_key, ev["topic_ko"])
            badge_color = "#7c3aed" if ev['days_until'] <= 14 else "#aaa"
            items_html.append(
                f'<div style="display:flex;align-items:flex-start;gap:8px;'
                f'padding:7px 0;border-bottom:1px solid #f3f0fa">'
                f'<span style="background:#ede9fe;color:{badge_color};font-size:11px;'
                f'font-weight:700;padding:2px 7px;border-radius:99px;white-space:nowrap">{d_str}</span>'
                f'<div><div style="font-size:12px;font-weight:600;color:#333">{name}</div>'
                f'<div style="font-size:11px;color:#888;margin-top:1px">{topic[:55]}…</div>'
                f'<div style="font-size:10px;color:#bbb;margin-top:1px">{ev["start_date"]}</div>'
                f'</div></div>'
            )
        lang_event_html[lang] = "".join(items_html)

    evt_panels = "".join(
        f'<div class="lang-content" data-lang="{lang}" '
        f'style="display:{"block" if lang=="ko" else "none"}">'
        f'{html}</div>'
        for lang, html in lang_event_html.items()
    )

    # ── 골든타임 행 ────────────────────────────────────────────────────
    golden_rows = "".join(
        f"<tr><td style='padding:2px 8px;font-size:12px;font-weight:600'>{p}</td>"
        f"<td style='padding:2px 8px;font-size:12px;color:#555'>{sched.golden_hours_label(p)}</td></tr>"
        for p in ["instagram", "threads", "facebook", "youtube"]
    )

    scheduled_cnt = sum(len(v) for v in by_date.values())

    return f"""
<div class="cal-widget">

  <!-- 헤더 + 언어 탭 -->
  <div class="cal-head">
    <div>
      <div class="cal-title">{_icon('calendar', 18, '#7c3aed')} 콘텐츠 캘린더</div>
      <div class="cal-sub">예약 대기 {scheduled_cnt}건 · 미예약 {len(unscheduled)}건</div>
    </div>
    <div class="lang-tabs">
      <button class="lang-btn active" id="tab-ko" onclick="setLang('ko')">한국어</button>
      <button class="lang-btn" id="tab-en" onclick="setLang('en')">English</button>
      <button class="lang-btn" id="tab-ja" onclick="setLang('ja')">日本語</button>
    </div>
  </div>

  <!-- 2컬럼: 7일 캘린더 + 시즌 이벤트 -->
  <div class="cal-body">

    <!-- 7일 그리드 -->
    <div class="cal-grid-col">
      <table class="cal-grid"><tr>{"".join(cols)}</tr></table>
      <details class="cal-golden">
        <summary>골든타임 기준</summary>
        <table style="margin-top:8px">{golden_rows}</table>
      </details>
    </div>

    <!-- 시즌 이벤트 -->
    <div class="cal-events">
      <div class="cal-events-title">{_icon('calendar-clock', 15, '#5b21b6')} 다가오는 이벤트</div>
      {evt_panels}
      <div class="cal-events-foot">D-14 도래 시 자동 캠페인 생성</div>
    </div>

  </div>
</div>"""


def build() -> str:
    items = publisher.list_items()
    n = len(items)
    approved = sum(1 for i in items if i["status"] == "APPROVED")
    fails = sum(1 for i in items if i["governance"] == "FAIL")
    warns = sum(1 for i in items if i["governance"] == "WARN")
    passes = sum(1 for i in items if i["governance"] == "PASS")

    cards = []
    for it in items:
        art = OUTPUT_DIR / it["slug"] / "article.md"
        raw = art.read_text(encoding="utf-8") if art.exists() else ""
        clean, had_schema = _publisher_view(raw)
        body_html = md.markdown(clean, extensions=["tables", "fenced_code"]) if clean else ""
        note = ("<p class='meta' style='color:#999;margin-top:10px'>✓ 검색·AI용 메타데이터는 "
                "자동 처리됩니다 — 게시자는 본문만 신경 쓰면 됩니다.</p>") if had_schema else ""
        cards.append(f"""
        <div class="card">
          <div class="card-head">
            <div>
              <div class="title">{it['title']}</div>
              <div class="meta">{_badge(it.get('kind','blog').upper())} {_badge(it['status'])} 검수 {_badge(it['governance'])}
                <code>{it['slug']}</code></div>
            </div>
            <div class="approve">{'✅ 발행 승인됨' if it['status']=='APPROVED'
              else f"대기 → <code>python main.py approve {it['slug']}</code>"}</div>
          </div>
          <details><summary>본문 보기 / 접기</summary>
            <div class="article">{body_html}{note}</div>
          </details>
        </div>""")

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wehome AI Marketing Engine</title>
<style>
  :root{{
    /* spacing — 8px grid */
    --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px;
    /* radius */
    --r-sm:6px; --r-md:10px; --r-lg:14px; --r-pill:999px;
    /* color */
    --violet:#7c3aed; --violet-dark:#5b21b6; --violet-tint:#f3f0f9; --violet-soft:#ede9fe;
    --ink:#1a1730; --muted:#6b6b76; --faint:#9b9aa6;
    --line:#ebe9f1; --bg:#faf9fc; --surface:#fff;
    --shadow:0 1px 3px rgba(20,12,48,.05);
    --shadow-lg:0 6px 22px rgba(124,58,237,.09);
  }}
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Pretendard',sans-serif;
    background:var(--bg);color:var(--ink);margin:0;padding:var(--s6);line-height:1.6;
    -webkit-font-smoothing:antialiased;letter-spacing:-.01em}}
  .wrap{{max-width:960px;margin:0 auto}}
  h1{{font-size:23px;font-weight:700;margin:0 0 var(--s1);color:var(--ink);
    display:flex;align-items:center;gap:var(--s2);letter-spacing:-.02em;
    padding-right:200px;min-height:36px}}
  .sub{{color:var(--muted);margin:0 0 var(--s4);font-size:14px}}
  .summary{{display:flex;gap:var(--s3);flex-wrap:wrap;margin-bottom:var(--s5)}}
  .stat{{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);
    padding:var(--s4) var(--s5);flex:1;min-width:120px;box-shadow:var(--shadow)}}
  .card{{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
    padding:var(--s5);margin-bottom:var(--s4);box-shadow:var(--shadow)}}
  .card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:var(--s4)}}
  .title{{font-size:16px;font-weight:700;display:flex;align-items:center;gap:var(--s2);
    letter-spacing:-.02em;color:var(--ink)}}
  .meta{{margin-top:var(--s2);font-size:12px;color:var(--muted);display:flex;gap:var(--s2);
    align-items:center;flex-wrap:wrap;font-weight:400}}
  .approve{{font-size:12px;color:var(--faint);text-align:right;min-width:160px;font-weight:400}}
  code{{background:var(--violet-tint);color:var(--violet-dark);padding:2px 6px;
    border-radius:var(--r-sm);font-size:12px}}
  details{{margin-top:var(--s3)}}
  summary{{cursor:pointer;color:var(--violet);font-weight:500;font-size:13px}}
  .article{{border-top:1px solid var(--line);margin-top:var(--s3);padding-top:var(--s3)}}
  .article table{{border-collapse:collapse;width:100%;margin:var(--s3) 0}}
  .article th,.article td{{border:1px solid var(--line);padding:var(--s2) var(--s3);font-size:14px;text-align:left}}
  .article pre{{background:#f7f6fb;padding:var(--s3);border-radius:var(--r-sm);overflow:auto;font-size:12px}}
  .article h1{{font-size:21px;color:var(--ink)}} .article h2{{font-size:17px;margin-top:var(--s5)}}
  /* buttons */
  .pub-btn,.gen-btn{{background:var(--violet);color:#fff;border:none;border-radius:var(--r-sm);
    padding:var(--s2) var(--s3);font-size:12px;font-weight:600;cursor:pointer;
    display:inline-flex;align-items:center;gap:5px;transition:background .15s,transform .05s}}
  .pub-btn:hover,.gen-btn:hover{{background:var(--violet-dark)}}
  .pub-btn:active,.gen-btn:active{{transform:translateY(1px)}}
  .pub-btn:disabled,.gen-btn:disabled{{opacity:.55;cursor:default}}
  .posted-tag{{display:inline-flex;align-items:center;gap:4px;color:#15803d;font-weight:600;font-size:12px}}
  /* generate form */
  .gen-form{{margin:var(--s3) 0;padding:var(--s4);background:var(--violet-tint);
    border:1px solid var(--violet-soft);border-radius:var(--r-md)}}
  .gen-form-title{{font-weight:600;font-size:14px;margin-bottom:var(--s3);
    display:flex;align-items:center;gap:6px;color:var(--ink)}}
  .gen-input{{width:62%;min-width:240px;padding:var(--s2) var(--s3);border:1px solid #d9cdf2;
    border-radius:var(--r-sm);font-size:14px;outline:none}}
  .gen-input:focus{{border-color:var(--violet)}}
  .gen-btn-row{{margin-top:var(--s3);display:flex;gap:var(--s2);flex-wrap:wrap}}
  .gen-btn{{background:#fff;color:var(--violet-dark);border:1px solid #d9cdf2}}
  .gen-btn:hover{{background:#fff;border-color:var(--violet);color:var(--violet)}}
  .gen-btn-primary{{background:var(--violet);color:#fff;border-color:var(--violet)}}
  .gen-btn-primary:hover{{background:var(--violet-dark);color:#fff}}
  .gen-form-hint{{font-size:12px;color:var(--faint);margin-top:var(--s2)}}
  /* calendar widget */
  .cal-widget{{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
    padding:var(--s5);margin-bottom:var(--s5);box-shadow:var(--shadow-lg)}}
  .cal-head{{display:flex;justify-content:space-between;align-items:center;
    margin-bottom:var(--s4);flex-wrap:wrap;gap:var(--s2)}}
  .cal-title{{font-size:16px;font-weight:600;display:flex;align-items:center;gap:var(--s2)}}
  .cal-sub{{font-size:12px;color:var(--faint);margin-top:2px}}
  .lang-tabs{{display:flex;gap:var(--s1);background:var(--violet-tint);padding:3px;border-radius:var(--r-sm)}}
  .lang-btn{{background:transparent;color:var(--muted);border:none;border-radius:var(--r-sm);
    padding:5px 12px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s}}
  .lang-btn.active{{background:var(--surface);color:var(--violet-dark);font-weight:600;box-shadow:var(--shadow)}}
  .cal-body{{display:flex;gap:var(--s5);align-items:flex-start;flex-wrap:wrap}}
  .cal-grid-col{{flex:2;min-width:0;overflow-x:auto}}
  .cal-grid{{border-collapse:separate;border-spacing:0;width:100%;min-width:560px}}
  .cal-golden{{margin-top:var(--s3)}}
  .cal-golden summary{{font-size:13px}}
  .cal-events{{flex:1;min-width:200px;max-width:280px;border-left:1px solid var(--line);padding-left:var(--s4)}}
  .cal-events-title{{font-size:13px;font-weight:600;color:var(--violet-dark);
    margin-bottom:var(--s3);display:flex;align-items:center;gap:6px}}
  .cal-events-foot{{font-size:11px;color:var(--faint);margin-top:var(--s2)}}
  /* sns nav */
  .sns-nav{{position:fixed;top:var(--s4);right:var(--s4);display:flex;gap:var(--s2);z-index:50}}
  .sns-ico{{width:32px;height:32px;border-radius:var(--r-sm);display:flex;align-items:center;
    justify-content:center;color:#fff;text-decoration:none;box-shadow:var(--shadow);transition:transform .12s}}
  .sns-ico:hover{{transform:translateY(-2px)}}
  .howto{{background:var(--violet-soft);color:var(--violet-dark);padding:var(--s3) var(--s4);
    border-radius:var(--r-md);font-size:13px;margin:0 0 var(--s5);display:flex;align-items:center;gap:var(--s2)}}
  .section-h{{font-size:16px;font-weight:600;margin:var(--s5) 0 var(--s3);
    display:flex;align-items:center;gap:var(--s2);letter-spacing:-.01em}}
  /* empty state */
  .empty-state{{display:flex;flex-direction:column;align-items:center;gap:var(--s3);
    padding:var(--s6) var(--s5);border:2px dashed var(--line);border-radius:var(--r-md);
    background:var(--violet-tint);margin-top:var(--s3);text-align:center}}
  .empty-title{{font-size:15px;font-weight:600;color:var(--violet-dark)}}
  .empty-sub{{font-size:13px;color:var(--faint);line-height:1.7}}
  /* stat numbers — typography weight tiers */
  .stat .num{{font-size:30px;font-weight:800;line-height:1.1;letter-spacing:-.04em}}
  .stat .lbl{{color:var(--faint);font-size:11px;font-weight:500;margin-top:var(--s1);text-transform:uppercase;letter-spacing:.04em}}
  @media (max-width:760px){{
    body{{padding:var(--s4)}}
    .wrap{{padding-top:52px}}
    h1{{font-size:19px;padding-right:0}}
    .card,.cal-widget{{padding:var(--s4)}}
    .stat{{min-width:calc(50% - var(--s2))}}
    .sns-ico{{width:28px;height:28px}}
  }}
</style></head>
<body>
<div class="sns-nav">
  <a class="sns-ico" style="background:#e1306c" href="https://www.instagram.com" target="_blank" title="Instagram">{_brand('instagram')}</a>
  <a class="sns-ico" style="background:#000" href="https://www.threads.net" target="_blank" title="Threads">{_brand('threads')}</a>
  <a class="sns-ico" style="background:#1877f2" href="https://www.facebook.com" target="_blank" title="Facebook">{_brand('facebook')}</a>
  <a class="sns-ico" style="background:#ff0000" href="https://www.youtube.com" target="_blank" title="YouTube">{_brand('youtube')}</a>
</div>
<div class="wrap">
  <h1>{_icon('sparkles', 22, '#7c3aed')} Wehome AI Marketing Engine</h1>
  <p class="sub">콘텐츠 자동 생성 현황 · 생성·검수 자동 / 사람 승인 후 발행</p>
  <p class="howto">{_icon('arrow-right', 16)} 본문만 복사해서 게시글을 작성하면 됩니다. (오른쪽 위 아이콘 = 해당 SNS로 이동)</p>
  <div class="summary">
    <div class="stat"><div class="num">{n}</div><div class="lbl">총 생성</div></div>
    <div class="stat"><div class="num">{approved}</div><div class="lbl">발행 승인됨</div></div>
    <div class="stat"><div class="num" style="color:#15803d">{passes}</div><div class="lbl">검수 PASS</div></div>
    <div class="stat"><div class="num" style="color:#7a5f00">{warns}</div><div class="lbl">검수 WARN</div></div>
    <div class="stat"><div class="num" style="color:#a8253a">{fails}</div><div class="lbl">검수 FAIL</div></div>
  </div>
  {_calendar_panel()}
  {_social_panel()}
  <h2 class="section-h">{_icon('file-text', 18, '#7c3aed')} 생성된 콘텐츠</h2>
  {''.join(cards)}
</div>
<script>
async function gen(platform, btn){{
  const t = (document.getElementById('genTopic').value || '').trim();
  if(!t){{ alert('주제를 입력하세요'); return; }}
  const old = btn.textContent; btn.disabled = true; btn.textContent = '생성 중…';
  try {{
    const r = await fetch('/api/social/generate?platform=' + platform + '&topic=' + encodeURIComponent(t));
    const j = await r.json();
    if (j.created) {{ location.reload(); }}
    else {{ alert('오류: ' + (j.error || '실패')); btn.disabled = false; btn.textContent = old; }}
  }} catch (e) {{
    alert('로컬 서버에서 열어야 동작합니다:\\n  python main.py serve');
    btn.disabled = false; btn.textContent = old;
  }}
}}
function setLang(lang) {{
  document.querySelectorAll('.lang-content').forEach(el => {{
    el.style.display = el.dataset.lang === lang ? 'block' : 'none';
  }});
  document.querySelectorAll('.lang-btn').forEach(btn => {{
    const active = btn.id === 'tab-' + lang;
    btn.style.background = active ? '#7c3aed' : '#f3f0f9';
    btn.style.color = active ? '#fff' : '#5b21b6';
  }});
}}
async function pub(id, btn){{
  const old = btn.textContent; btn.disabled = true; btn.textContent = '게시 중…';
  try {{
    const r = await fetch('/api/social/publish?id=' + encodeURIComponent(id));
    const j = await r.json();
    if (j.status === 'posted') {{ btn.textContent = '✓ 게시됨'; }}
    else if (j.status === 'dry-run') {{ btn.disabled = false; btn.textContent = old;
      alert('dry-run (실제 게시 안 됨): ' + (j.reason || '') + '\\n.env에 토큰을 넣으면 실게시됩니다.'); }}
    else {{ btn.textContent = old; btn.disabled = false; alert('오류: ' + (j.error || j.msg || '실패')); }}
  }} catch (e) {{
    btn.textContent = old; btn.disabled = false;
    alert('로컬 서버에서 열어야 동작합니다:\\n  python main.py serve');
  }}
}}
</script>
</body></html>"""


def write() -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "index.html"
    path.write_text(build(), encoding="utf-8")
    return str(path)
