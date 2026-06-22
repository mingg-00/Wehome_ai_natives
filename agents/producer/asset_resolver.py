from __future__ import annotations                         # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화

import hashlib                                             # URL을 해싱하여 고유한 캐시 파일 이름을 생성하기 위해 hashlib 모듈을 사용
import os                                                  # 파일 경로 처리를 위해 표준 라이브러리의 os 모듈을 사용
import shutil                                              # 기존 실행 번호 기반 캐시를 공용 캐시 파일로 복사하기 위해 shutil 모듈을 사용
from urllib.parse import urlparse                          # URL을 파싱하여 파일 이름과 확장자를 추출하기 위해 urllib.parse의 urlparse 함수를 사용
from urllib.request import Request, urlopen                # 원격 이미지를 다운로드하기 위해 urllib.request의 Request와 urlopen 함수를 사용

from PIL import Image                                      # 이미지 유효성 검사를 위해 Pillow 라이브러리의 Image 모듈을 사용

from config.settings import ensure_directories, settings   # 애플리케이션 설정과 디렉토리 생성 헬퍼 함수를 가져오기 위해 config.settings 모듈에서 가져옴


# 원격 URL에서 이미지를 다운로드하여 로컬 캐시에 저장하고, 로컬 파일 시스템에서 이미지 경로를 해결하는 클래스
class AssetResolver:

    # 생성자에서 자산 디렉토리를 받아 초기화하며, run_number는 기존 호출부와의 호환성을 위해 받지만 이미지 캐시 파일명에는 사용하지 않음
    def __init__(self, assets_dir: str, run_number: int | None = None) -> None:
        self.assets_dir = assets_dir
        self.run_number = run_number


    # 스토리보드에서 자산 이름을 받아 로컬 파일 시스템에서 해당 경로를 확인하거나, URL인 경우 원격 이미지를 다운로드하여 캐시된 경로를 반환하는 메인 메서드
    def resolve_image_path(self, asset_name: str) -> str | None:
        if not asset_name:
            return None

        if asset_name.startswith(("http://", "https://")):
            return self._resolve_remote_image_path(asset_name)

        local_path = os.path.join(self.assets_dir, asset_name)
        if os.path.exists(local_path):
            return local_path
        return None


    # 원격 이미지 URL을 받아 캐시 디렉토리에 다운로드하여 저장하는 내부 메서드로, 콘텐츠 유형과 크기를 검사하여 유효한 이미지 파일로 저장하며, 다운로드된 파일이 유효한 이미지인지 검증
    def _resolve_remote_image_path(self, asset_url: str) -> str | None:
        cache_dir = os.path.join(self.assets_dir, "downloaded")
        ensure_directories(cache_dir)

        parsed_url = urlparse(asset_url)
        filename = os.path.basename(parsed_url.path) or "downloaded_image"
        _, file_ext = os.path.splitext(filename)
        if not file_ext:
            file_ext = ".jpg"

        cache_name = hashlib.sha1(asset_url.encode("utf-8")).hexdigest()
        cached_path = self._build_downloaded_asset_path(cache_dir, cache_name, file_ext)
        if os.path.exists(cached_path) and self.is_valid_image_file(cached_path):
            return cached_path

        legacy_cached_path = self._find_valid_run_scoped_cache(cache_dir, cache_name, file_ext)
        if legacy_cached_path:
            shutil.copy2(legacy_cached_path, cached_path)
            return cached_path

        try:
            self.download_image_asset(asset_url, cached_path)
            print(f"[ProducerAgent] 이미지 자산 다운로드 완료: {asset_url} -> {cached_path}")
            return cached_path
        except (OSError, ValueError) as exc:
            print(f"[ProducerAgent] 이미지 자산 다운로드 실패: {asset_url} -> {exc}")
            return None

    
    # 원격 이미지를 다운로드하는 메서드로, URL을 요청하여 콘텐츠 유형과 크기를 검사한 후 유효한 이미지 파일로 저장
    def download_image_asset(self, asset_url: str, output_path: str) -> None:
        request = Request(
            asset_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; WehomeVideoAgent/1.0)"},
        )
        temp_path = f"{output_path}.tmp"

        try:
            with urlopen(request, timeout=settings.request_timeout_seconds) as response:
                content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if content_type and not self.is_allowed_image_content_type(content_type):
                    raise ValueError(f"예상하지 못한 이미지 콘텐츠 유형입니다: {content_type}")

                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > settings.image_download_max_bytes:
                    raise ValueError(
                        f"이미지 파일이 너무 큽니다: {content_length}바이트 "
                        f"(최대 {settings.image_download_max_bytes}바이트)"
                    )

                bytes_read = 0
                with open(temp_path, "wb") as file_handle:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        bytes_read += len(chunk)
                        if bytes_read > settings.image_download_max_bytes:
                            raise ValueError(
                                f"이미지 파일이 너무 큽니다: {bytes_read}바이트 "
                                f"(최대 {settings.image_download_max_bytes}바이트)"
                            )
                        file_handle.write(chunk)

            if not self.is_valid_image_file(temp_path):
                raise ValueError("다운로드한 파일이 유효한 래스터 이미지가 아닙니다.")
            os.replace(temp_path, output_path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    # 캐시 디렉토리와 해시된 파일 이름을 기반으로 다운로드된 자산의 전체 경로를 빌드하는 내부 메서드
    def _build_downloaded_asset_path(self, cache_dir: str, cache_name: str, file_ext: str) -> str:
        return os.path.join(cache_dir, f"{cache_name}{file_ext}")

    # 이전 버전에서 생성한 실행 번호 기반 캐시 파일을 찾아 공용 캐시로 승격하기 위한 내부 메서드
    def _find_valid_run_scoped_cache(self, cache_dir: str, cache_name: str, file_ext: str) -> str | None:
        try:
            filenames = os.listdir(cache_dir)
        except OSError:
            return None

        suffix = f"_{cache_name}{file_ext}"
        for filename in sorted(filenames):
            if not filename.startswith("downloaded_") or not filename.endswith(suffix):
                continue

            candidate_path = os.path.join(cache_dir, filename)
            if self.is_valid_image_file(candidate_path):
                return candidate_path
        return None

    # 허용된 이미지 콘텐츠 유형인지 확인하는 정적 메서드로, 다운로드된 파일이 유효한 이미지인지 검증하기 위해 콘텐츠 유형을 검사
    @staticmethod
    def is_allowed_image_content_type(content_type: str) -> bool:
        return content_type in {
            "application/octet-stream",
            "binary/octet-stream",
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/webp",
            "image/gif",
            "image/bmp",
            "image/tiff",
        }

    # 유효한 이미지 파일인지 확인하는 정적 메서드로, Pillow 라이브러리를 사용하여 이미지 파일의 유효성을 검사
    @staticmethod
    def is_valid_image_file(image_path: str) -> bool:
        try:
            with Image.open(image_path) as image:
                image.verify()
            with Image.open(image_path) as image:
                image.load()
                return image.width > 0 and image.height > 0
        except (OSError, ValueError):
            return False
