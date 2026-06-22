from __future__ import annotations   # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화

import os                            # 파일 경로 처리를 위해 표준 라이브러리의 os 모듈을 사용
from dataclasses import dataclass    # 데이터 클래스 데코레이터를 가져와 BGM 후보를 정의
from pathlib import Path             # 파일 경로를 객체 지향적으로 다루기 위해 표준 라이브러리의 pathlib 모듈을 사용
from typing import Any               # Any 타입을 사용하여 스토리보드의 구조를 유연하게 처리


# BGM 후보를 나타내는 데이터 클래스
@dataclass(frozen=True)
class BgmCandidate:
    path: str
    score: int


# BGM 선택기를 정의하는 클래스
class BgmSelector:
    """Select a local BGM track that best matches the storyboard mood.

    This is intentionally lightweight so the selection policy can later be
    replaced with a Hicksfield or other API-backed recommendation service.
    """

    # BGM 후보를 수집하고 스토리보드의 분위기에 맞게 점수를 매겨 최적의 BGM 경로를 선택하는 메인 메서드
    def __init__(self, bgm_dir: str) -> None:
        self.bgm_dir = bgm_dir

    # 스토리보드의 분위기에 맞게 점수를 매긴 후보 목록에서 가장 높은 점수를 가진 BGM 경로를 선택하는 메서드
    def select_bgm_path(self, storyboard: dict[str, Any]) -> str | None:
        candidates = self.rank_candidates(storyboard)
        if not candidates:
            print(f"[BgmSelector] 로컬 BGM 후보가 없습니다. 폴더를 확인하세요: {self.bgm_dir}")
            return None

        ranked_candidates = sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                Path(candidate.path).name.lower(),
            ),
        )
        selected_candidate = ranked_candidates[0]
        print(f"[BgmSelector] 로컬 BGM 선택 완료: {selected_candidate.path} (점수={selected_candidate.score})")
        return selected_candidate.path

    # BGM 후보를 수집하는 내부 메서드로, 지정된 디렉토리를 탐색하여 지원되는 오디오 파일을 후보 목록으로 반환
    def _collect_candidates(self) -> list[BgmCandidate]:
        if not os.path.isdir(self.bgm_dir):
            return []

        supported_extensions = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
        candidates: list[BgmCandidate] = []

        for root, _, files in os.walk(self.bgm_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                extension = Path(file_path).suffix.lower()
                if extension not in supported_extensions:
                    continue
                candidates.append(BgmCandidate(path=file_path, score=0))

        return candidates

    # 스토리보드의 분위기에 맞게 BGM 후보에 점수를 매기는 메서드로, 스토리보드에서 분위기를 나타내는 텍스트를 추출하고 후보 파일 이름과 비교하여 점수를 계산
    def score_candidate(self, candidate_path: str, storyboard: dict[str, Any]) -> int:
        mood_text = self._gather_storyboard_text(storyboard)
        file_text = self._normalize_text(candidate_path)

        keyword_groups = {
            "calm": {"calm", "soft", "piano", "relax", "warm", "cozy", "ambient", "dream", "gentle"},
            "energetic": {"energetic", "upbeat", "bright", "hype", "rhythm", "pop", "fast", "modern"},
            "luxury": {"luxury", "premium", "elegant", "cinematic", "classy", "sophisticated", "ambient"},
            "travel": {"travel", "road", "vacation", "adventure", "light", "fresh", "sunny"},
        }

        score = 0
        for label, keywords in keyword_groups.items():
            if any(keyword in mood_text for keyword in keywords):
                score += 3 if any(keyword in file_text for keyword in keywords) else 1

        if not score:
            for keyword in mood_text.split():
                if keyword and keyword in file_text:
                    score += 1

        if not score:
            score = 1

        return score

    # 스토리보드의 분위기에 맞게 BGM 후보를 순위를 매기는 메서드
    def rank_candidates(self, storyboard: dict[str, Any]) -> list[BgmCandidate]:
        candidates = self._collect_candidates()
        ranked_candidates: list[BgmCandidate] = []
        for candidate in candidates:
            ranked_candidates.append(
                BgmCandidate(
                    path=candidate.path,
                    score=self.score_candidate(candidate.path, storyboard),
                )
            )
        return ranked_candidates

    # 스토리보드에서 분위기를 나타내는 텍스트를 추출하는 내부 메서드로, 스토리보드의 메타데이터와 장면 설명에서 텍스트를 모아 하나의 문자열로 반환
    def _gather_storyboard_text(self, storyboard: dict[str, Any]) -> str:
        video_metadata = storyboard.get("video_metadata", {})
        scenes = storyboard.get("scenes", [])
        hashtags = storyboard.get("recommended_hashtags", [])

        parts: list[str] = []
        if isinstance(video_metadata, dict):
            parts.extend(
                str(video_metadata.get(field, ""))
                for field in ("concept", "bgm_mood", "target_audience")
            )
        for scene in scenes:
            if isinstance(scene, dict):
                parts.extend(
                    str(scene.get(field, ""))
                    for field in ("section", "camera_effect", "caption", "tts_script")
                )
        parts.extend(str(tag) for tag in hashtags)
        return self._normalize_text(" ".join(parts))
    
    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(value.lower().split())
