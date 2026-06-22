from __future__ import annotations

import os
import shutil
import json
from typing import Any

from config.settings import settings
from agents.delivery import DeliveryAgent, DeliveryError
from agents.director import StoryboardAgent, StoryboardError
from agents.producer import ProducerAgent
from agents.scraper import build_company_profile, crawl_company_site


def load_company_input() -> dict[str, Any]:
    # 회사 모드에서는 웹사이트에서 읽어온 자료를 프로필로 정리해 스토리보드 입력으로 사용한다.
    pages = crawl_company_site()
    profile = build_company_profile(pages, brand_name=settings.company_brand_name)
    return {
        "brand_name": profile.brand_name,
        "source_urls": profile.source_urls,
        "pages": profile.pages,
        "summary_points": profile.summary_points,
        "image_urls": profile.image_urls,
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


def cleanup_artifact(path: str) -> None:
    # 전송이 끝난 뒤에는 재생성 가능한 산출물만 지우고, 폴더 자체는 유지한다.
    if os.path.isdir(path):
        for entry_name in os.listdir(path):
            entry_path = os.path.join(path, entry_name)
            try:
                if os.path.isdir(entry_path):
                    shutil.rmtree(entry_path)
                else:
                    os.remove(entry_path)
            except OSError as exc:
                print(f"[Main] Cleanup skipped for {entry_path}: {exc}")
        return

    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as exc:
            print(f"[Main] Cleanup skipped for {path}: {exc}")


def main() -> int:
    # 각 단계는 독립된 Agent로 분리되어 있어 실패 지점을 쉽게 확인할 수 있다.
    print("[Main] Company storyboard generation started.")
    storyboard_agent = StoryboardAgent()
    producer_agent = ProducerAgent()
    delivery_agent = DeliveryAgent()
    output_video_path = ""
    sent_to_discord = False

    try:
        print("[Main] Company profile loading started.")
        input_data = load_company_input()
        print(f"[Main] Company profile ready: {input_data.get('brand_name', '')}")
    except Exception as exc:
        print(f"[Main] Company profile stage failed: {exc}")
        return 1

    try:
        # 1단계: Gemini에서 스토리보드를 가져오거나 캐시를 재사용한다.
        storyboard = storyboard_agent.generate_storyboard(
            input_data,
        )
        print("[Main] Storyboard ready.")
    except StoryboardError as exc:
        print(f"[Main] Storyboard stage failed: {exc}")
        return 1

    try:
        # 2단계: 스토리보드 JSON을 기반으로 실제 영상 파일을 만든다.
        output_video_path = producer_agent.render_video(storyboard)
        print(f"[Main] Video rendered: {output_video_path}")
    except Exception as exc:
        print(f"[Main] Video rendering failed: {exc}")
        cleanup_artifact("output/temp_audio")
        return 1

    try:
        # 3단계: 설정에 따라 디스코드 전송을 수행하거나 건너뛴다.
        caption = build_company_caption(input_data, storyboard)
        sent_to_discord = delivery_agent.send_video(output_video_path, caption)
    except DeliveryError as exc:
        print(f"[Main] Delivery stage failed: {exc}")
        cleanup_artifact("output/temp_audio")
        return 1
    except Exception as exc:
        print(f"[Main] Unexpected delivery error: {exc}")
        cleanup_artifact("output/temp_audio")
        return 1

    # 임시 오디오는 결과와 무관하게 정리하고, 최종 영상만 남긴다.
    cleanup_artifact("output/temp_audio")

    if not sent_to_discord:
        print("[Main] Discord delivery is disabled. Local final video was kept.")

    print("[Main] Pipeline completed successfully.")
    return 0


if __name__ == "__main__":
    # main()의 종료 코드를 운영체제에 전달해 배치 실행에서도 결과를 확인할 수 있게 한다.
    raise SystemExit(main())
