import json
import os
import re

import discord
from discord.ext import tasks
from pathlib import Path
from dotenv import load_dotenv

# .env를 engine 모듈 import 전에 로드해야 Settings 클래스가 올바른 값을 읽는다
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from engine import social, governance, schedule as sched, events as evt, multilang
from engine import trends as trend_engine, property_monitor as prop_mon
from engine import activity_log as _alog


def _friendly_error(error: str) -> str:
    """Raw 에러 문자열 → 사람이 읽기 쉬운 한 줄 메시지."""
    http_match = re.search(r"HTTP (\d+)", error)
    http_code = int(http_match.group(1)) if http_match else None

    meta_code, meta_msg = None, ""
    json_match = re.search(r"\{.*\}", error, re.DOTALL)
    if json_match:
        try:
            err = json.loads(json_match.group()).get("error", {})
            meta_code = err.get("code")
            meta_msg = err.get("message", "")
        except Exception:
            pass

    if http_code == 402 or "CreditsDepleted" in error:
        return "크레딧 소진 (무료 플랜 한도 초과)"
    if meta_code == 190 or "could not be decrypted" in error:
        return "토큰 만료 → 재발급 필요"
    if "API access blocked" in error and meta_code == 200:
        return "Meta 개발자 계정 제한 중 (계정 인증 완료 후 재시도)"
    if "Cannot call API for app" in error:
        return "페이지 토큰 권한 없음 → FB_PAGE_TOKEN 재발급 필요"
    if meta_msg:
        return f"Meta 오류: {meta_msg}"
    if http_code:
        return f"HTTP {http_code} 오류"
    return error[:120]

# =========================
# 설정
# =========================

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
# 예약 게시 결과 알림을 보낼 채널 ID (선택, .env의 DISCORD_NOTIFY_CHANNEL)
NOTIFY_CHANNEL_ID = int(os.getenv("DISCORD_NOTIFY_CHANNEL", "0") or "0")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# Discord 메시지ID -> (SNS 큐 데이터, 생성 시각)
# TTL 1시간 — 반응 없이 방치된 항목 자동 제거
import time as _time
import datetime as _dt
_PENDING_TTL = 3600
pending_posts: dict[int, tuple[dict, float]] = {}
_campaign_triggered_date: str = ""  # 날짜별 중복 트리거 방지

# 모든 플랫폼 골든타임(KST 정시) → UTC 변환하여 루프 실행 시각 목록 생성
_KST = _dt.timezone(_dt.timedelta(hours=9))
_UTC = _dt.timezone.utc
_golden_times = sorted({
    _dt.time(hour=(h - 9) % 24, minute=0, tzinfo=_UTC)
    for hours in sched.GOLDEN_HOURS.values()
    for h in hours
})  # 결과: UTC 0,2,3,4,6,9,10,11,12시 = KST 9,11,12,13,15,18,19,20,21시


_PLAT_ICON = {
    "threads": "🧵", "facebook": "📘", "instagram": "📸",
    "youtube": "▶️", "x": "𝕏", "pinterest": "📌",
}

def _post_preview(item: dict) -> str:
    """큐 아이템 → 읽기 쉬운 한 줄 미리보기."""
    text = item.get("text", "")
    platform = item.get("platform", "")
    icon = _PLAT_ICON.get(platform, "📢")
    at = item.get("scheduled_at", "")
    time_str = ""
    if at:
        try:
            t = _dt.datetime.fromisoformat(at)
            KST = _dt.timezone(_dt.timedelta(hours=9))
            if t.tzinfo is None:
                t = t.replace(tzinfo=KST)
            time_str = f" · ⏰ {t.astimezone(KST).strftime('%m/%d %H:%M')}"
        except Exception:
            pass
    preview = text[:55] + ("…" if len(text) > 55 else "")
    return f"{icon} **{platform.upper()}**{time_str}\n> {preview}"


def _cleanup_pending():
    now = _time.time()
    expired = [mid for mid, (_, ts) in pending_posts.items() if now - ts > _PENDING_TTL]
    for mid in expired:
        del pending_posts[mid]


# ---------------------------------------------------------------------------
# 백그라운드: 골든타임 정시에만 실행 (KST 9·11·12·13·15·18·19·20·21시)
# ---------------------------------------------------------------------------
@tasks.loop(time=_golden_times)
async def _auto_publish_loop():
    results = social.publish(due_only=True)
    if results:
        lines = ["⏰ **예약 게시 자동 실행**\n"]
        for r in results:
            if r["status"] == "posted":
                lines.append(f"✅ {r['platform']} 게시 완료 (id={r.get('id')})")
            elif r["status"] == "dry-run":
                lines.append(f"👀 {r['platform']} dry-run — {r.get('reason','')}")
            else:
                lines.append(f"❌ {r['platform']} 오류: {r.get('error','')}")
        msg = "\n".join(lines)
        print(msg)
        if NOTIFY_CHANNEL_ID:
            ch = client.get_channel(NOTIFY_CHANNEL_ID)
            if ch:
                await ch.send(msg)

    await _check_seasonal_campaigns()
    await _check_trends()
    await _check_new_properties()


async def _check_seasonal_campaigns():
    """D-14 이벤트가 있으면 다국어 캠페인 초안을 채널에 알림 (하루 1회)."""
    global _campaign_triggered_date
    KST = _dt.timezone(_dt.timedelta(hours=9))
    today = _dt.datetime.now(KST).strftime("%Y-%m-%d")
    if _campaign_triggered_date == today:
        return  # 오늘 이미 체크했으면 스킵
    _campaign_triggered_date = today

    due = evt.due_campaigns()
    if not due:
        return

    ch = client.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None

    for campaign in due:
        print(f"🗓️ 시즌 캠페인 트리거: {campaign['name_ko']} (D-{campaign['lead_days']})")
        _alog.append("campaign", f"시즌 캠페인 자동 생성 — {campaign['name_ko']}", detail=f"D-{campaign['days_until']} / {campaign['start_date']}")

        platforms = ["threads", "facebook", "instagram"]
        topic_by_lang = {
            "ko": campaign["topic_ko"],
            "en": campaign["topic_en"],
            "ja": campaign["topic_ja"],
        }

        lang_labels = {"ko": "🇰🇷 한국어", "en": "🇺🇸 English", "ja": "🇯🇵 日本語"}
        notify_lines = [
            f"🗓️ **시즌 캠페인 자동 생성** — {campaign['name_ko']}",
            f"📅 이벤트 시작: {campaign['start_date']} (D-{campaign['days_until']})",
            "─────────────────────",
        ]

        # 언어별 큐 적재
        ml_posts = multilang.generate_posts_multilang(topic_by_lang, platforms)
        for lang, posts in ml_posts.items():
            if lang == "_mode":
                continue
            label = lang_labels.get(lang, lang)
            notify_lines.append(f"\n**{label}**")
            for platform in platforms:
                post = posts.get(platform)
                if not post:
                    continue
                item = social.enqueue(
                    platform=platform,
                    topic=topic_by_lang.get(lang, campaign["topic_ko"]),
                    post=post,
                    governance="PASS",
                    scheduled_at=sched.next_golden_time(platform),
                )
                notify_lines.append(_post_preview(item))

        notify_lines.append("\n👍 지금 즉시 게시  |  📅 골든타임 예약")
        msg = "\n".join(notify_lines)
        print(msg)
        if ch:
            await ch.send(msg)


async def _check_trends():
    """Google Trends 감지 — 위홈 연관 트렌드 있으면 포스팅 초안 생성 (하루 1회)."""
    KST = _dt.timezone(_dt.timedelta(hours=9))
    today = _dt.datetime.now(KST).strftime("%Y-%m-%d")
    # 시즌 캠페인과 같은 날짜 가드 공유 (이미 오늘 실행됐으면 스킵)
    if getattr(_check_trends, "_last_date", "") == today:
        return
    _check_trends._last_date = today

    print("[Trends] Google Trends 체크 중...")
    topics = trend_engine.get_campaign_topics(max_topics=3)
    if not topics:
        return

    ch = client.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
    platforms = ["threads", "facebook", "instagram"]

    for topic in topics:
        _alog.append("trend", f"트렌드 감지 — {topic['keyword']}", detail=topic["topic_ko"][:80])
        lines = [
            f"🔥 **트렌드 캠페인 자동 생성** — `{topic['keyword']}`",
            f"📍 주제: {topic['topic_ko']}",
            "─────────────────────",
        ]
        for platform in platforms:
            post = social.generate_posts(topic["topic_ko"], [platform]).get(platform)
            if not post:
                continue
            item = social.enqueue(
                platform=platform,
                topic=topic["topic_ko"],
                post=post,
                governance="PASS",
                scheduled_at=sched.next_golden_time(platform),
            )
            lines.append(_post_preview(item))

        lines.append("\n👍 지금 즉시 게시  |  📅 골든타임 예약")
        msg = "\n".join(lines)
        print(msg)
        if ch:
            await ch.send(msg)


async def _check_new_properties():
    """신규 숙소 감지 → 맞춤 포스팅 자동 생성 (하루 1회)."""
    KST = _dt.timezone(_dt.timedelta(hours=9))
    today = _dt.datetime.now(KST).strftime("%Y-%m-%d")
    if getattr(_check_new_properties, "_last_date", "") == today:
        return
    _check_new_properties._last_date = today

    print("[PropertyMonitor] 신규 숙소 체크 중...")
    new_props = prop_mon.detect_new_properties(max_new=3)
    if not new_props:
        return

    ch = client.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
    platforms = ["threads", "facebook", "instagram"]

    for prop in new_props:
        _alog.append("property", f"신규 숙소 감지 — {prop.title}", detail=f"{prop.region_ko} / {prop.room_url}")
        lines = [
            f"🏠 **신규 숙소 감지** — {prop.title}",
            f"📍 지역: {prop.region_ko}  |  🔗 {prop.room_url}",
            "─────────────────────",
        ]
        for platform in platforms:
            post = social.generate_posts(
                prop.topic_ko, [platform],
                source=f"숙소 URL: {prop.room_url}\n이미지: {prop.image_url}"
            ).get(platform)
            if not post:
                continue
            if prop.image_url and platform == "instagram":
                post["image_url"] = prop.image_url
            item = social.enqueue(
                platform=platform,
                topic=prop.topic_ko,
                post=post,
                governance="PASS",
                scheduled_at=sched.next_golden_time(platform),
            )
            lines.append(_post_preview(item))

        lines.append("\n👍 지금 즉시 게시  |  📅 골든타임 예약")
        msg = "\n".join(lines)
        print(msg)
        if ch:
            await ch.send(msg)


@client.event
async def on_ready():
    print("=" * 60)
    print(f"🤖 로그인 완료: {client.user}")
    print("📡 [POST_REQUEST] 감시 시작")
    print("=" * 60)
    _auto_publish_loop.start()


@client.event
async def on_message(message):

    print("=" * 50)
    print("첨부파일 개수:", len(message.attachments))
    for a in message.attachments:
        print("첨부파일:", a.filename)
    print("메시지 감지!")
    print("채널:", message.channel)
    print("작성자:", message.author)
    print("내용:", message.content)

    # 자기 자신의 메시지만 무시 (다른 봇/앱의 [POST_REQUEST]는 처리)
    if message.author.id == client.user.id:
        return

    if not message.content.startswith("[POST_REQUEST]"):
        return

    topic = (
        message.content
        .replace("[POST_REQUEST]", "")
        .strip()
    )

    if not topic:
        await message.reply(
            "⚠️ 형식:\n\n[POST_REQUEST]\n주제 입력"
        )
        return

    # 첨부파일(mp4 등 영상) 처리
    video_path = None

    if message.attachments:
        attachment = message.attachments[0]
        if attachment.filename.lower().endswith(
            (".mp4", ".mov", ".avi", ".mkv")
        ):
            os.makedirs("uploads", exist_ok=True)
            video_path = os.path.join("uploads", os.path.basename(attachment.filename))
            await attachment.save(video_path)
            print("🎥 영상 저장 완료")
            print("📁", video_path)
            print("존재 여부:", os.path.exists(video_path))

    await message.add_reaction("👀")

    print(f"\n🔔 포스팅 요청 감지")
    print(f"주제: {topic}")

    platforms = [
        "threads",
        "facebook",
        "instagram",
        "youtube",
        # "x",  # 쓰기 크레딧 리셋 후 주석 해제 (developer.x.com → Dashboard → Usage 확인)
    ]

    # 영상 첨부 시 캡션을 그대로 사용 (GPT 재생성 불필요)
    if video_path:
        posts = {
            p: {"text": topic, "caption": topic, "link": "https://www.wehome.me",
                "pin_title": topic[:90], "pin_description": topic, "image_text": ""}
            for p in platforms
        }
        preview_label = "📝 영상 포스팅 초안 (캡션 그대로 사용)\n\n"
    else:
        posts = social.generate_posts(topic=topic, platforms=platforms)
        preview_label = "📝 SNS 초안 생성 완료\n\n"

    created_ids = []

    preview = preview_label
    preview += f"주제: {topic[:100]}\n\n"

    for platform in platforms:

        post = posts.get(platform)

        if not post:
            continue

        text = social.render(platform, post)

        report = governance.review(
            {
                "_kind": "social",
                "topic": topic,
                "platform": platform
            },
            text
        )

        golden = sched.next_golden_time(platform)

        item = social.enqueue(
            platform=platform,
            topic=topic,
            post=post,
            governance=report["status"],
            scheduled_at=golden,   # 기본값: 다음 골든타임으로 예약
            video_path=video_path,
        )

        created_ids.append(item["id"])

        golden_label = sched.golden_hours_label(platform)
        preview += (
            f"[{platform.upper()}] 골든타임: {golden_label}\n"
            f"{text[:500]}\n\n"
        )

    preview += (
        "👍 지금 즉시 게시\n"
        "📅 다음 골든타임에 예약 게시\n"
        "❌ 검수 FAIL 상태는 자동 차단됩니다."
    )

    draft_msg = await message.reply(preview)

    # pending_posts를 반응 추가 전에 등록 (타이밍 레이스 방지)
    _cleanup_pending()
    pending_posts[draft_msg.id] = ({"ids": created_ids, "video_path": video_path}, _time.time())

    await draft_msg.add_reaction("👍")
    await draft_msg.add_reaction("📅")


@client.event
async def on_reaction_add(reaction, user):

    # 봇 자신의 반응 무시 (user.bot + id 이중 확인)
    if user.bot or user.id == client.user.id:
        return

    emoji = str(reaction.emoji)
    if emoji not in ("👍", "📅"):
        return

    message_id = reaction.message.id

    if message_id not in pending_posts:
        return

    # 📅: 골든타임 예약 (즉시 게시 안 함, APPROVED만 설정)
    if emoji == "📅":
        data, _ = pending_posts.pop(message_id)
        ids = data["ids"]
        lines = ["📅 **골든타임 예약 결과**\n"]
        q_map = {it["id"]: it for it in social.queue()}
        for item_id in ids:
            result = social.approve(item_id)
            it = q_map.get(item_id, {})
            plat = it.get("platform", "").upper()
            if not result.get("ok"):
                lines.append(f"❌ {plat} 예약 불가 — {result.get('msg', '검수 FAIL')}")
                continue
            at = it.get("scheduled_at", "?")
            golden_label = sched.golden_hours_label(it.get("platform", ""))
            lines.append(f"✅ {plat} → {at[:16]} (골든타임 {golden_label})")
        lines.append("\n⏰ 예약 시간이 되면 자동 게시됩니다.")
        await reaction.message.reply("\n".join(lines))
        return

    # 👍: 즉시 게시

    data, _ = pending_posts.pop(message_id)
    ids = data["ids"]
    video_path = data["video_path"]

    print("👍 즉시 게시 승인됨")
    result_text = "🚀 SNS 게시 시작\n\n"

    for item_id in ids:
        social.approve(item_id)
        result = social.publish_one(item_id)

        if result.get("status") == "posted":
            result_text += f"✅ {item_id}\n"
        elif result.get("status") == "dry-run":
            result_text += f"👀 {item_id}\n   (토큰 없음 → dry-run)\n"
        else:
            friendly = _friendly_error(result.get("error", "알 수 없는 오류"))
            result_text += f"❌ {item_id}\n   {friendly}\n"

    await reaction.message.reply(result_text)


if not DISCORD_BOT_TOKEN:
    print("❌ DISCORD_BOT_TOKEN이 .env에 없습니다.")
    print("   .env에 DISCORD_BOT_TOKEN=your_token 을 추가하세요.")
else:
    client.run(DISCORD_BOT_TOKEN)
