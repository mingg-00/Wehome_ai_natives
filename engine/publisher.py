"""발행 게이트.

생성된 콘텐츠를 output/<slug>/ 에 '초안(DRAFT)'으로 저장한다.
사람이 approve() 하기 전에는 절대 APPROVED가 되지 않는다(= 발행 승인 게이트).
검수(governance)에서 FAIL이 있으면 승인 자체를 막는다.
"""
from __future__ import annotations

import datetime
import json

from .config import OUTPUT_DIR


def _dir(slug: str):
    d = OUTPUT_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_draft(content, markdown, report, faq_schema=None, article_schema=None) -> str:
    d = _dir(content["slug"])
    (d / "article.md").write_text(markdown, encoding="utf-8")
    (d / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    if faq_schema is not None:
        (d / "faq_schema.json").write_text(json.dumps(faq_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    if article_schema is not None:
        (d / "article_schema.json").write_text(json.dumps(article_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    title = content.get("title_tag") or content.get("title") or content.get("pin_title") or content["topic"]
    (d / "status.json").write_text(json.dumps({
        "slug": content["slug"],
        "topic": content["topic"],
        "title": title,
        "kind": content.get("_kind", "blog"),
        "status": "DRAFT",
        "governance": report["status"],
        "generated_at": content["generated_at"],
        "approved_at": None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(d)


def approve(slug: str) -> dict:
    d = OUTPUT_DIR / slug
    sf = d / "status.json"
    if not sf.exists():
        return {"ok": False, "msg": f"'{slug}' 초안을 찾을 수 없습니다."}
    st = json.loads(sf.read_text(encoding="utf-8"))
    if st["governance"] == "FAIL":
        return {"ok": False, "msg": f"검수 FAIL 상태라 승인 불가. 재생성/수정 후 승인하세요."}
    st["status"] = "APPROVED"
    st["approved_at"] = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
    sf.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "msg": f"✅ '{slug}' 발행 승인 완료. output/{slug}/article.md 를 CMS에 게시하세요."}


def list_items() -> list[dict]:
    if not OUTPUT_DIR.exists():
        return []
    items = []
    for sf in sorted(OUTPUT_DIR.glob("*/status.json")):
        items.append(json.loads(sf.read_text(encoding="utf-8")))
    return items
