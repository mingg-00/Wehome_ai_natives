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


def _cleanup_pending():
    now = _time.time()
    expired = [mid for mid, (_, ts) in pending_posts.items() if now - ts > _PENDING_TTL]
    for mid in expired:
        del pending_posts[mid]


# ---------------------------------------------------------------------------
# 백그라운드: 예약 시각 도래한 APPROVED 항목 자동 게시 (5분마다)
# ---------------------------------------------------------------------------
@tasks.loop(minutes=5)
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
            "",
        ]

        # 언어별 큐 적재
        ml_posts = multilang.generate_posts_multilang(topic_by_lang, platforms)
        for lang, posts in ml_posts.items():
            if lang == "_mode":
                continue
            label = lang_labels.get(lang, lang)
            notify_lines.append(f"**{label}** 초안 생성 완료")
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
                notify_lines.append(f"  • {platform}: {item['id']}")

        notify_lines.append("\n👍 개별 게시물 승인 후 골든타임에 자동 발행됩니다.")
        msg = "\n".join(notify_lines)
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

    posts = social.generate_posts(
        topic=topic,
        platforms=platforms
    )

    created_ids = []

    preview = "📝 SNS 초안 생성 완료\n\n"
    preview += f"주제: {topic}\n\n"

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
        lines = ["📅 **골든타임 예약 완료**\n"]
        for item_id in ids:
            social.approve(item_id)
            q = {it["id"]: it for it in social.queue()}
            it = q.get(item_id, {})
            plat = it.get("platform", "")
            at = it.get("scheduled_at", "?")
            golden_label = sched.golden_hours_label(plat)
            lines.append(f"✅ {plat.upper()} → {at[:16]} (골든타임 {golden_label})")
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
