#!/usr/bin/env python3
"""Wehome AI Marketing Engine — CLI.

콘텐츠 자동 생성 → 자동 검수 → (사람 승인) → 발행.
사람은 'approve' 한 번만 누른다. 나머지는 자동.

사용 예:
  python main.py list                      # 토픽 백로그 + 생성 현황
  python main.py generate --next           # ICE 최상위 토픽 자동 생성
  python main.py generate "Topic ..."      # 특정 주제 생성
  python main.py generate --auto 3         # 상위 3개 연속 생성
  python main.py review <slug>             # 검수 리포트 다시 보기
  python main.py approve <slug>            # ✅ 사람 발행 승인 (게이트)
  python main.py status                     # 생성물 상태 목록
"""
from __future__ import annotations

import argparse
import json

from engine import (channels, dashboard, generator, governance, monitor,
                    publisher, reddit_radar, server, social)
from engine.config import DATA_DIR, settings


def _load_topics() -> list[dict]:
    return json.loads((DATA_DIR / "topics.json").read_text(encoding="utf-8"))


def _done() -> set:
    return {(it["topic"], it.get("kind", "blog")) for it in publisher.list_items()}


def _run_one(topic: str, fmt: str = "blog", primary_keyword: str = "") -> None:
    print(f"\n🛠  생성 중 [{fmt}]: {topic}")
    if fmt == "blog":
        content = generator.generate(topic, primary_keyword)
        faq = generator.build_faq_schema(content)
        art = generator.build_article_schema(content)
        markdown = generator.render_markdown(content, faq, art)
        report = governance.review(content, markdown)
        path = publisher.save_draft(content, markdown, report, faq, art)
    else:
        content = channels.generate(topic, fmt, primary_keyword)
        markdown = channels.render_markdown(content)
        report = governance.review(content, markdown)
        path = publisher.save_draft(content, markdown, report)
    print(f"   모드: {content['_mode']}  →  저장: {path}/article.md")
    print(governance.format_report(report))
    if report["status"] == "FAIL":
        print("   🚫 검수 FAIL → 승인 불가. 수정/재생성 필요.")
    else:
        print(f"   다음: python main.py approve {content['slug']}")


def cmd_list(_):
    done = {topic for topic, _kind in _done()}
    print("📋 토픽 백로그 (ICE順)")
    for t in sorted(_load_topics(), key=lambda x: -x["ice"]):
        mark = "✅생성됨" if t["topic"] in done else "⬜미생성"
        print(f"  [{t['ice']:>2}] {mark}  {t['topic']}")


def cmd_generate(args):
    fmts = list(channels.FORMATS) + ["blog"] if args.format == "all" else [args.format]
    if args.topic:
        for f in fmts:
            _run_one(args.topic, f, args.keyword or "")
    else:
        topics = sorted(_load_topics(), key=lambda x: -x["ice"])
        done = _done()
        n = args.auto if args.auto else 1
        made = 0
        for f in fmts:
            pending = [t for t in topics if (t["topic"], f) not in done]
            for t in pending[:n]:
                _run_one(t["topic"], f, t["primary_keyword"])
                made += 1
        if made == 0:
            print("🎉 요청한 포맷의 토픽이 이미 모두 생성되었습니다.")
    print(f"\n🖥  대시보드 갱신: {dashboard.write()}  (브라우저로 열어 확인)")


def cmd_review(args):
    d = publisher.OUTPUT_DIR / args.slug
    cf = d / "content.json"
    mf = d / "article.md"
    if not cf.exists():
        print(f"'{args.slug}' 초안을 찾을 수 없습니다.")
        return
    content = json.loads(cf.read_text(encoding="utf-8"))
    report = governance.review(content, mf.read_text(encoding="utf-8"))
    print(governance.format_report(report))


def cmd_approve(args):
    print(publisher.approve(args.slug)["msg"])
    dashboard.write()


def cmd_social_gen(args):
    plats = [p.strip() for p in args.platforms.split(",")] if args.platforms else social.PLATFORMS
    print(f"📱 SNS 포스트 생성 [{', '.join(plats)}]: {args.topic}\n")
    posts = social.generate_posts(args.topic, plats, args.source or "")
    for p in plats:
        post = posts.get(p)
        if not post:
            continue
        text = social.render(p, post)
        report = governance.review({"_kind": "social", "topic": args.topic, "platform": p}, text)
        item = social.enqueue(p, args.topic, post, report["status"], args.at)
        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "🚫"}[report["status"]]
        print(f"  {icon} {p:<10} {item['id']}")
        print(f"       {text[:90].replace(chr(10),' ')}…")
    print(f"\n🖥  대시보드 갱신: {dashboard.write()}")
    print("승인: python main.py social-approve <id>  ·  게시: python main.py social-publish")


def cmd_social_check(_):
    print("🔌 SNS 연결 상태 (게시 없이 점검)\n")
    for r in social.connection_status():
        icon = "✅" if r["ready"] else "⚪"
        print(f"  {icon} {r['platform']:<10} {r['mode']:<10} {r['note']}")
    print("\n✅=토큰 연결됨(실게시)  ⚪=dry-run. .env에 토큰 넣으면 ✅로 바뀝니다. (가이드: SNS_연결가이드.md)")


def cmd_social_queue(_):
    items = social.queue()
    if not items:
        print("SNS 큐가 비어 있습니다. 'social-gen'으로 생성하세요.")
        return
    print("📱 SNS 큐")
    for it in items:
        icon = {"POSTED": "🚀", "APPROVED": "✅", "DRAFT": "📝"}.get(it["status"], "·")
        sched = it.get("scheduled_at") or "asap"
        print(f"  {icon} [{it['status']:<8}] {it['platform']:<10} 검수={it['governance']:<4} {sched}  {it['id']}")


def cmd_social_approve(args):
    print(social.approve(args.id)["msg"])
    dashboard.write()


def cmd_social_publish(args):
    if not settings.llm_enabled:
        pass
    results = social.publish(due_only=args.due)
    if not results:
        print("게시할 APPROVED 항목이 없습니다 (먼저 social-approve).")
        return
    for r in results:
        if r["status"] == "posted":
            print(f"  🚀 {r['platform']} 게시 완료 (id={r.get('id')})")
        elif r["status"] == "dry-run":
            print(f"  👀 {r['platform']} dry-run — {r['reason']}\n       {r['preview'][:90]}…")
        else:
            print(f"  🚫 {r['platform']} 오류: {r.get('error')}")
    dashboard.write()


def cmd_dashboard(_):
    print(f"🖥  대시보드 생성: {dashboard.write()}\n   브라우저로 이 파일을 열어 확인하세요.")
    print("   ※ '🚀 지금 게시' 버튼을 쓰려면: python main.py serve")


def cmd_serve(args):
    server.serve(port=args.port, open_browser=not args.no_browser)


def cmd_radar(args):
    print("📡 Reddit 기회 레이더 — 최근 관련 스레드 검색 중 (읽기 전용)...\n")
    ops = reddit_radar.find_opportunities()
    if ops is None:
        print("⚠️ Reddit 검색에 실패했습니다 (네트워크/차단). 잠시 후 재시도하세요.")
        return
    if not ops:
        print("최근 한 달 내 관련 스레드를 찾지 못했습니다.")
        return
    print(f"🔎 관련 스레드 {len(ops)}개 발견. 상위 일부에 답변 초안을 생성합니다:\n")
    n = args.auto if args.auto else 3
    for t in ops[:n]:
        content = reddit_radar.draft_for(t)
        md = reddit_radar.render_markdown(content)
        report = governance.review(content, md)
        publisher.save_draft(content, md, report)
        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "🚫"}[report["status"]]
        print(f"  {icon} {t['title'][:70]}")
        print(f"      {t['url']}")
        print(f"      초안: output/{content['slug']}/article.md\n")
    print(f"🖥  대시보드 갱신: {dashboard.write()}")
    print("※ 자동 게시 아님 — 대시보드에서 검토 후 직접 올리세요.")


def cmd_monitor(args):
    wt = getattr(args, "with_tools", False)
    label = "도구 장착(MCP 연동 시뮬레이션)" if wt else "기준선(도구 없음)"
    print(f"📡 AI 노출 모니터 실행 중 — {label}...\n")
    snap = monitor.run(with_tools=wt)
    if snap is None:
        print("⚠️ OPENAI_API_KEY가 필요합니다 (모니터는 LLM 호출).")
        return
    print(monitor.format_report(snap))
    base = monitor.latest("baseline")
    tools = monitor.latest("with-tools")
    if base and tools:
        print(f"\n📈 SoAV 비교  기준선 {base['soav']}%  →  MCP 도구 장착 {tools['soav']}%")
    dashboard.write()
    print("\n🖥  대시보드 갱신됨.")


def cmd_status(_):
    items = publisher.list_items()
    if not items:
        print("아직 생성된 콘텐츠가 없습니다. 'python main.py generate --next'로 시작하세요.")
        return
    print("📦 생성물 상태")
    for it in items:
        icon = "✅" if it["status"] == "APPROVED" else "📝"
        print(f"  {icon} [{it['status']:>8}] 검수={it['governance']:<4} {it['slug']}")


def main():
    if not settings.llm_enabled:
        print("ℹ️  OPENAI_API_KEY 미설정 → 오프라인 스켈레톤 모드 (구조/스키마/검수만 시연).\n")
    p = argparse.ArgumentParser(description="Wehome AI Marketing Engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="토픽 백로그 + 생성 현황").set_defaults(func=cmd_list)

    g = sub.add_parser("generate", help="콘텐츠 생성")
    g.add_argument("topic", nargs="?", help="생성할 주제(생략 시 백로그에서 자동 선택)")
    g.add_argument("--next", action="store_true", help="ICE 최상위 미생성 토픽 1개 생성")
    g.add_argument("--auto", type=int, metavar="N", help="상위 N개 연속 생성")
    g.add_argument("--keyword", help="primary keyword 지정")
    g.add_argument("--format", choices=["blog", "reddit", "shortform", "pinterest", "all"],
                   default="blog", help="콘텐츠 포맷 (기본 blog)")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("review", help="검수 리포트 보기")
    r.add_argument("slug")
    r.set_defaults(func=cmd_review)

    a = sub.add_parser("approve", help="✅ 사람 발행 승인 (게이트)")
    a.add_argument("slug")
    a.set_defaults(func=cmd_approve)

    sub.add_parser("status", help="생성물 상태 목록").set_defaults(func=cmd_status)
    sub.add_parser("dashboard", help="🖥 시각 대시보드(HTML) 생성").set_defaults(func=cmd_dashboard)
    sv = sub.add_parser("serve", help="🌐 대시보드 서버('🚀 지금 게시' 버튼 동작)")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--no-browser", action="store_true", help="브라우저 자동 열기 끔")
    sv.set_defaults(func=cmd_serve)

    sg = sub.add_parser("social-gen", help="📱 SNS 포스트 생성→검수→예약큐")
    sg.add_argument("topic")
    sg.add_argument("--platforms", help="쉼표구분 (기본: instagram,threads,x,pinterest,facebook)")
    sg.add_argument("--source", help="기반 소스 텍스트(예: 보도 스토리)")
    sg.add_argument("--at", help="예약 시각 ISO (생략 시 asap)")
    sg.set_defaults(func=cmd_social_gen)
    sub.add_parser("social-check", help="🔌 SNS 연결 상태 점검").set_defaults(func=cmd_social_check)
    sub.add_parser("social-queue", help="📱 SNS 큐 보기").set_defaults(func=cmd_social_queue)
    sa = sub.add_parser("social-approve", help="✅ SNS 게시 승인")
    sa.add_argument("id")
    sa.set_defaults(func=cmd_social_approve)
    spx = sub.add_parser("social-publish", help="🚀 승인된 SNS 게시 (실제/dry-run)")
    spx.add_argument("--due", action="store_true", help="예약시간 도래분만 게시")
    spx.set_defaults(func=cmd_social_publish)
    m = sub.add_parser("monitor", help="📡 AI 노출(위홈 추천/인용) 측정")
    m.add_argument("--with-tools", action="store_true",
                   help="위홈 MCP 도구를 AI에 쥐여주고 측정 (등록 시 효과 증명)")
    m.set_defaults(func=cmd_monitor)
    rad = sub.add_parser("radar", help="📡 Reddit 기회 탐색 + 답변 초안(사람이 게시)")
    rad.add_argument("--auto", type=int, metavar="N", help="상위 N개 스레드에 초안 생성")
    rad.set_defaults(func=cmd_radar)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
