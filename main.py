from __future__ import annotations

import argparse
from typing import Any
from urllib.parse import urlparse

from config.settings import get_next_artifact_number, settings
from agents.delivery import DeliveryAgent, DeliveryError
from agents.director import StoryboardAgent, StoryboardError
from agents.producer import ProducerAgent
from agents.scraper import build_company_profile, crawl_company_site


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="회사 웹사이트 기반 홍보 영상을 생성합니다.")
    parser.add_argument(
        "--url",
        action="append",
        dest="source_urls",
        help="크롤링할 회사 웹사이트 URL입니다. 여러 개를 넣으려면 --url을 반복해서 사용하세요.",
    )
    parser.add_argument("--brand-name", help="영상에 사용할 회사/브랜드명입니다.")
    parser.add_argument(
        "--requirements",
        help="영상에 반영할 사용자 요구사항입니다. 예: 차분하고 고급스러운 분위기, 20대 여성 타깃, 숙박 예약 CTA 강조",
    )
    return parser.parse_args()


def _normalize_source_url(url_value: str) -> str:
    cleaned_url = url_value.strip()
    if not cleaned_url:
        return ""
    parsed_url = urlparse(cleaned_url)
    if not parsed_url.scheme:
        return f"https://{cleaned_url}"
    return cleaned_url


def _input_with_default(prompt: str, default_value: str = "") -> str:
    if default_value:
        entered_value = input(f"{prompt} [{default_value}]: ").strip()
        return entered_value or default_value
    return input(f"{prompt}: ").strip()


def _read_runtime_input(args: argparse.Namespace) -> dict[str, Any]:
    default_source_urls = [_normalize_source_url(url) for url in settings.company_source_urls]
    default_source_urls = [url for url in default_source_urls if url]
    source_urls = [_normalize_source_url(url) for url in args.source_urls or []]
    source_urls = [url for url in source_urls if url]
    brand_name = (args.brand_name or settings.company_brand_name or "").strip()
    user_requirements = (args.requirements or settings.video_user_requirements or "").strip()

    try:
        if args.source_urls is None:
            default_url_text = ", ".join(default_source_urls)
            entered_url = _input_with_default("크롤링할 회사 웹사이트 URL을 입력하세요", default_url_text)
            normalized_url = _normalize_source_url(entered_url)
            if normalized_url:
                source_urls = [url for url in (_normalize_source_url(url) for url in entered_url.split(",")) if url]
        if args.brand_name is None:
            brand_name = _input_with_default("브랜드명을 입력하세요(비워두면 자동 추론)", brand_name)
        if args.requirements is None:
            user_requirements = _input_with_default("영상에 반영할 요구사항을 자연어로 입력하세요(선택)", user_requirements)
    except EOFError as exc:
        raise ValueError("--url 또는 COMPANY_SOURCE_URLS로 크롤링할 웹사이트 URL을 전달하세요.") from exc

    if not source_urls:
        raise ValueError("크롤링할 웹사이트 URL이 필요합니다. --url 또는 COMPANY_SOURCE_URLS를 설정하세요.")

    return {
        "source_urls": source_urls,
        "brand_name": brand_name,
        "user_requirements": user_requirements,
    }


def load_company_input(
    source_urls: list[str],
    brand_name: str = "",
    user_requirements: str = "",
    run_number: int | None = None,
) -> dict[str, Any]:
    # 회사 모드에서는 웹사이트에서 읽어온 자료를 프로필로 정리해 스토리보드 입력으로 사용한다.
    pages = crawl_company_site(urls=source_urls)
    profile = build_company_profile(pages, brand_name=brand_name, run_number=run_number)
    return {
        "brand_name": profile.brand_name,
        "source_urls": profile.source_urls,
        "pages": profile.pages,
        "summary_points": profile.summary_points,
        "image_urls": profile.image_urls,
        "user_requirements": user_requirements,
    }


def build_company_caption(company_input: dict[str, Any], storyboard: dict[str, Any]) -> str:
    # 회사 소개 영상용 업로드 본문을 만든다.
    concept_title = storyboard["video_metadata"]["concept"]
    hashtags = " ".join(storyboard.get("recommended_hashtags", []))
    brand_name = company_input.get("brand_name") or "회사 소개"
    return (
        f"[{brand_name}] 브랜드 소개 영상\n\n"
        f"영상 콘셉트: {concept_title}\n\n"
        f"{hashtags}"
    )


def main() -> int:
    # 각 단계는 독립된 Agent로 분리되어 있어 실패 지점을 쉽게 확인할 수 있다.
    args = parse_args()
    run_number = get_next_artifact_number(
        "output",
        settings.video_dir,
        settings.audio_dir,
        settings.assets_dir,
    )
    print(f"[Main] 회사 소개 영상 생성 시작. 실행 번호={run_number:03d}")
    storyboard_agent = StoryboardAgent(run_number=run_number)
    producer_agent = ProducerAgent(run_number=run_number)
    delivery_agent = DeliveryAgent()
    output_video_path = ""
    sent_to_discord = False

    try:
        runtime_input = _read_runtime_input(args)
        print(f"[Main] 크롤링 대상 URL: {', '.join(runtime_input['source_urls'])}")
        if runtime_input["user_requirements"]:
            print(f"[Main] 사용자 요구사항 반영 예정: {runtime_input['user_requirements']}")
        print("[Main] 회사 프로필 불러오는 중.")
        input_data = load_company_input(
            source_urls=runtime_input["source_urls"],
            brand_name=runtime_input["brand_name"],
            user_requirements=runtime_input["user_requirements"],
            run_number=run_number,
        )
        print(f"[Main] 회사 프로필 준비 완료: {input_data.get('brand_name', '')}")
    except Exception as exc:
        print(f"[Main] 회사 프로필 단계 실패: {exc}")
        return 1

    try:
        # 1단계: Gemini에서 스토리보드를 가져오거나 캐시를 재사용한다.
        storyboard = storyboard_agent.generate_storyboard(
            input_data,
        )
        print("[Main] 스토리보드 준비 완료.")
    except StoryboardError as exc:
        print(f"[Main] 스토리보드 단계 실패: {exc}")
        return 1

    try:
        # 2단계: 스토리보드 JSON을 기반으로 실제 영상 파일을 만든다.
        output_video_path = producer_agent.render_video(storyboard)
        print(f"[Main] 영상 렌더링 완료: {output_video_path}")
    except Exception as exc:
        print(f"[Main] 영상 렌더링 실패: {exc}")
        return 1

    try:
        # 3단계: 설정에 따라 디스코드 전송을 수행하거나 건너뛴다.
        caption = build_company_caption(input_data, storyboard)
        sent_to_discord = delivery_agent.send_video(output_video_path, caption)
    except DeliveryError as exc:
        print(f"[Main] 전송 단계 실패: {exc}")
        return 1
    except Exception as exc:
        print(f"[Main] 전송 중 예상치 못한 오류: {exc}")
        return 1

    if not sent_to_discord:
        print("[Main] Discord 전송이 꺼져 있어 로컬 영상 파일만 보관했습니다.")

    print("[Main] 전체 파이프라인 완료.")
    return 0


if __name__ == "__main__":
    # main()의 종료 코드를 운영체제에 전달해 배치 실행에서도 결과를 확인할 수 있게 한다.
    raise SystemExit(main())
