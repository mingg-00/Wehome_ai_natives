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

_BADGE = {
    "APPROVED": ("#0a7d28", "#e3f7e8"),
    "DRAFT": ("#8a6d00", "#fdf3d0"),
    "PASS": ("#0a7d28", "#e3f7e8"),
    "WARN": ("#8a6d00", "#fdf3d0"),
    "FAIL": ("#b00020", "#fde3e6"),
}


def _badge(text: str) -> str:
    fg, bg = _BADGE.get(text, ("#5b21b6", "#ede9fe"))
    return (f'<span style="background:{bg};color:{fg};padding:2px 10px;'
            f'border-radius:999px;font-size:12px;font-weight:700">{text}</span>')


def _publisher_view(text: str) -> tuple[str, bool]:
    """게시자 화면용: 본문(2번)만. 1)메타·3·4)schema는 숨김(파일엔 보존)."""
    start = text.find("## 2)")
    end = text.find("\n## 3)")
    if start != -1:
        body = text[start:end] if end != -1 else text[start:]
        nl = body.find("\n")
        return (body[nl + 1:].strip() if nl != -1 else body.strip()), True
    return (text[:end].rstrip() if end != -1 else text.rstrip()), (end != -1)


_GEN_FORM = """
  <div style="margin:12px 0;padding:14px;background:#f3eff9;border:1px solid #e3dcf3;border-radius:10px">
    <div style="font-weight:700;margin-bottom:8px">✨ 새 SNS 글 생성 — 주제 입력 후 플랫폼 선택</div>
    <input id="genTopic" placeholder="예: K-pop concert stay in Korea / 합법 숙박 꿀팁"
           style="width:62%;min-width:240px;padding:8px;border:1px solid #cdbff0;border-radius:8px;font-size:14px">
    <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
      <button class="gen-btn" onclick="gen('x',this)">𝕏 X</button>
      <button class="gen-btn" onclick="gen('instagram',this)">IG</button>
      <button class="gen-btn" onclick="gen('threads',this)">@ Threads</button>
      <button class="gen-btn" onclick="gen('pinterest',this)">P Pinterest</button>
      <button class="gen-btn" onclick="gen('facebook',this)">f Facebook</button>
      <button class="gen-btn" style="background:#5b21b6" onclick="gen('all',this)">전체 생성</button>
    </div>
    <div style="font-size:12px;color:#888;margin-top:6px">선택한 플랫폼의 형식으로 AI가 자동 작성 → 아래 큐에 추가됩니다.</div>
  </div>"""


def _social_panel() -> str:
    q = social.queue()
    rows = []
    for it in q:
        st = _badge(it["status"])
        gov = _badge(it["governance"])
        if it["status"] == "POSTED":
            btn = "🚀 게시됨"
        elif it["governance"] == "FAIL":
            btn = "<span style='color:#b00020'>검수 FAIL</span>"
        else:
            btn = (f"<button class='pub-btn' onclick=\"pub('{it['id']}', this)\">"
                   f"🚀 지금 게시</button>")
        rows.append(f"<tr><td>{_badge(it['platform'].upper())}</td><td>{st} {gov}</td>"
                    f"<td>{it['text'][:140]}</td><td style='white-space:nowrap'>{btn}</td></tr>")
    posted = sum(1 for it in q if it["status"] == "POSTED")
    appr = sum(1 for it in q if it["status"] == "APPROVED")
    table = (f"""<details open><summary>큐 보기 ({len(q)}건)</summary><div class="article"><table>
        <tr><th>플랫폼</th><th>상태/검수</th><th>문안</th><th>게시</th></tr>{''.join(rows)}
      </table></div></details>""" if q else
             '<p class="meta" style="color:#999">아직 생성된 글이 없습니다 — 위에서 주제를 입력하고 플랫폼을 누르세요.</p>')
    return f"""<div class="card">
      <div class="title">📱 SNS 자동 포스팅 (자사 계정)</div>
      <div class="meta">총 {len(q)}건 · 승인 {appr} · 게시 {posted} · "🚀 지금 게시" = 승인+즉시 게시(토큰 없으면 dry-run)</div>
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
<div style="background:#fff;border:1px solid #e8e6ee;border-radius:14px;
  padding:18px 22px;margin-bottom:20px;box-shadow:0 2px 8px rgba(124,58,237,.06)">

  <!-- 헤더 + 언어 탭 -->
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px">
    <div>
      <div style="font-size:16px;font-weight:700">📅 콘텐츠 캘린더</div>
      <div style="font-size:12px;color:#888;margin-top:2px">
        예약 대기 {scheduled_cnt}건 · 미예약 {len(unscheduled)}건
      </div>
    </div>
    <div style="display:flex;gap:6px">
      <button class="lang-btn active" id="tab-ko" onclick="setLang('ko')"
        style="background:#7c3aed;color:#fff;border:none;border-radius:8px;
        padding:5px 12px;font-size:13px;font-weight:700;cursor:pointer">🇰🇷 한국어</button>
      <button class="lang-btn" id="tab-en" onclick="setLang('en')"
        style="background:#f3f0f9;color:#5b21b6;border:none;border-radius:8px;
        padding:5px 12px;font-size:13px;font-weight:700;cursor:pointer">🇺🇸 English</button>
      <button class="lang-btn" id="tab-ja" onclick="setLang('ja')"
        style="background:#f3f0f9;color:#5b21b6;border:none;border-radius:8px;
        padding:5px 12px;font-size:13px;font-weight:700;cursor:pointer">🇯🇵 日本語</button>
    </div>
  </div>

  <!-- 2컬럼: 7일 캘린더 + 시즌 이벤트 -->
  <div style="display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap">

    <!-- 7일 그리드 -->
    <div style="flex:2;min-width:0;overflow-x:auto">
      <table style="border-collapse:collapse;width:100%;min-width:560px">
        <tr>{"".join(cols)}</tr>
      </table>
      <div style="margin-top:10px">
        <details>
          <summary style="cursor:pointer;color:#7c3aed;font-weight:600;font-size:13px">
            골든타임 기준
          </summary>
          <table style="margin-top:6px">{golden_rows}</table>
        </details>
      </div>
    </div>

    <!-- 시즌 이벤트 -->
    <div style="flex:1;min-width:200px;max-width:280px;border-left:1px solid #f0eef8;padding-left:16px">
      <div style="font-size:13px;font-weight:700;color:#5b21b6;margin-bottom:8px">
        🗓️ 다가오는 이벤트
      </div>
      {evt_panels}
      <div style="font-size:11px;color:#bbb;margin-top:8px">
        D-14 도래 시 자동 캠페인 생성
      </div>
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
  body{{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;
    background:#faf9fc;color:#1a1a1a;margin:0;padding:32px;line-height:1.6}}
  .wrap{{max-width:920px;margin:0 auto}}
  h1{{font-size:24px;margin:0 0 4px;color:#7c3aed}}
  .sub{{color:#666;margin:0 0 16px}}
  .summary{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:28px}}
  .stat{{background:#fff;border:1px solid #e8e6ee;border-radius:12px;padding:14px 20px;flex:1;min-width:120px}}
  .stat .num{{font-size:28px;font-weight:800}}
  .stat .lbl{{color:#777;font-size:13px}}
  .card{{background:#fff;border:1px solid #e8e6ee;border-radius:12px;padding:18px 22px;margin-bottom:16px}}
  .card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}}
  .title{{font-size:17px;font-weight:700}}
  .meta{{margin-top:6px;font-size:13px;color:#555;display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
  .approve{{font-size:12px;color:#555;text-align:right;min-width:160px}}
  code{{background:#f1eef8;padding:1px 6px;border-radius:5px;font-size:12px}}
  details{{margin-top:12px}}
  summary{{cursor:pointer;color:#7c3aed;font-weight:600;font-size:14px}}
  .article{{border-top:1px solid #eee;margin-top:12px;padding-top:12px}}
  .article table{{border-collapse:collapse;width:100%;margin:10px 0}}
  .article th,.article td{{border:1px solid #ddd;padding:6px 10px;font-size:14px;text-align:left}}
  .article pre{{background:#f6f8fa;padding:12px;border-radius:8px;overflow:auto;font-size:12px}}
  .article h1{{font-size:22px;color:#1a1a1a}} .article h2{{font-size:18px;margin-top:20px}}
  .pub-btn{{background:#7c3aed;color:#fff;border:none;border-radius:8px;padding:6px 12px;
    font-size:13px;font-weight:700;cursor:pointer}}
  .pub-btn:hover{{background:#5b21b6}} .pub-btn:disabled{{opacity:.6;cursor:default}}
  .gen-btn{{background:#7c3aed;color:#fff;border:none;border-radius:8px;padding:7px 12px;
    font-size:13px;font-weight:700;cursor:pointer}}
  .gen-btn:hover{{opacity:.9}} .gen-btn:disabled{{opacity:.6;cursor:default}}
  .sns-nav{{position:fixed;top:16px;right:16px;display:flex;gap:8px;z-index:50}}
  .sns-ico{{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;
    justify-content:center;color:#fff;font-weight:800;font-size:15px;text-decoration:none;
    box-shadow:0 1px 4px rgba(0,0,0,.25)}}
  .sns-ico:hover{{opacity:.85}}
  .howto{{background:#ede9fe;border:1px solid #d8d0f0;color:#5b21b6;padding:10px 14px;
    border-radius:10px;font-size:14px;margin:0 0 20px}}
</style></head>
<body>
<div class="sns-nav">
  <a class="sns-ico" style="background:#dc2743;font-size:12px" href="https://www.instagram.com" target="_blank" title="Instagram으로 이동">IG</a>
  <a class="sns-ico" style="background:#111" href="https://www.threads.net" target="_blank" title="Threads로 이동">@</a>
  <a class="sns-ico" style="background:#1877f2" href="https://www.facebook.com" target="_blank" title="Facebook으로 이동">f</a>
  <a class="sns-ico" style="background:#ff0000;font-size:18px" href="https://www.youtube.com" target="_blank" title="YouTube로 이동">▶</a>
</div>
<div class="wrap">
  <h1>🤖 Wehome AI Marketing Engine</h1>
  <p class="sub">콘텐츠 자동 생성 현황 · 생성·검수 자동 / 사람 승인 후 발행</p>
  <p class="howto">👉 본문만 복사해서 게시글을 작성하면 됩니다. (오른쪽 위 아이콘 = 해당 SNS로 이동)</p>
  <div class="summary">
    <div class="stat"><div class="num">{n}</div><div class="lbl">총 생성</div></div>
    <div class="stat"><div class="num">{approved}</div><div class="lbl">발행 승인됨</div></div>
    <div class="stat"><div class="num" style="color:#0a7d28">{passes}</div><div class="lbl">검수 PASS</div></div>
    <div class="stat"><div class="num" style="color:#8a6d00">{warns}</div><div class="lbl">검수 WARN</div></div>
    <div class="stat"><div class="num" style="color:#b00020">{fails}</div><div class="lbl">검수 FAIL</div></div>
  </div>
  {_calendar_panel()}
  {_social_panel()}
  <h2 style="font-size:18px;margin:24px 0 12px">📝 생성된 콘텐츠</h2>
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
    if (j.status === 'posted') {{ btn.textContent = '🚀 게시됨'; }}
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
