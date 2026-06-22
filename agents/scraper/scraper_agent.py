from __future__ import annotations                # Python 3.10+에서 타입 힌트에 대한 미래 기능을 활성화

import json                                       # 회사 프로필을 JSON 파일로 저장하기 위해 사용
import os                                         # 저장 경로의 디렉터리를 만들기 위해 사용
import re                                         # 파일명 번호 매기기를 위해 사용
import time                                       # 크롤링 경과 시간을 측정하기 위해 사용
from dataclasses import asdict, dataclass, field  # 데이터 클래스와 관련된 유틸리티를 가져온다.
from html.parser import HTMLParser                # HTML 파싱을 위해 표준 라이브러리의 HTMLParser를 사용
from typing import Any                            # URL에서 텍스트와 이미지 정보를 추출하기 위한 간단한 크롤러와 프로필 빌더
from urllib.parse import urljoin                  # URL을 절대 경로로 변환하기 위한 유틸리티
from urllib.request import Request, urlopen       # 웹 페이지 요청과 응답 처리를 위한 표준 라이브러리

from config.settings import settings              # 설정에서 회사 웹사이트 URL과 크롤링 관련 타임아웃, 페이지 수 제한 등을 읽어옴


# 회사 웹사이트에서 추출한 페이지 정보를 담는 간단한 데이터 클래스
@dataclass(frozen=True)
class CompanyPageSnapshot:
    url: str
    title: str
    meta_description: str
    canonical_url: str = ""
    og_title: str = ""
    og_description: str = ""
    og_image_url: str = ""
    headings: list[str] = field(default_factory=list)
    body_text: str = ""
    image_urls: list[str] = field(default_factory=list)


# 회사 웹사이트에서 추출한 여러 페이지의 정보를 종합해 영상 기획에 활용할 프로필을 만듦
@dataclass(frozen=True)
class CompanyProfile:
    brand_name: str
    source_urls: list[str]
    pages: list[dict[str, Any]]
    summary_points: list[str]
    image_urls: list[str]


# 회사 웹사이트에서 텍스트와 이미지 정보를 추출해 페이지별 스냅샷을 만들고, 여러 페이지를 종합해 영상 기획용 프로필을 빌드하는 함수들
class _CompanyPageParser(HTMLParser):
    
    # HTMLParser를 상속받아 회사 웹사이트의 HTML을 파싱하고, 제목, 메타 설명, 헤딩, 본문 텍스트, 이미지 URL 등을 추출하는 커스텀 파서
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.title_text = ""
        self.meta_description = ""
        self.canonical_url = ""
        self.og_title = ""
        self.og_description = ""
        self.og_image_url = ""
        self.headings: list[str] = []
        self.body_chunks: list[str] = []
        self.image_urls: list[str] = []
        self._capture_heading = False
        self._heading_chunks: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    # HTML 태그를 처리하고, 필요한 정보를 추출하는 로직을 구현
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return

        if self._ignored_depth:
            return

        attr_map = {name.lower(): value for name, value in attrs if value is not None}
        if tag == "title":
            self._in_title = True
        elif tag in {"h1", "h2", "h3"}:
            self._capture_heading = True
            self._heading_chunks = []
        elif tag in {"img", "source"}:
            self._collect_image_sources(attr_map)
        elif tag == "link":
            rel = (attr_map.get("rel") or "").lower()
            href = attr_map.get("href")
            if "canonical" in rel and href and not self.canonical_url:
                self.canonical_url = self._resolve_url(href)
        elif tag == "meta":
            name = (attr_map.get("name") or "").lower()
            property_name = (attr_map.get("property") or "").lower()
            meta_key = name or property_name
            content = (attr_map.get("content") or "").strip()

            if name == "description" and not self.meta_description:
                self.meta_description = content
            elif meta_key in {"og:title", "twitter:title"} and content and not self.og_title:
                self.og_title = content
            elif meta_key in {"og:description", "twitter:description"} and content and not self.og_description:
                self.og_description = content
            elif meta_key in {"og:image", "og:image:url", "twitter:image"} and content:
                image_url = self._resolve_url(content)
                if image_url and not self.og_image_url:
                    self.og_image_url = image_url
                self._add_unique_image_url(image_url)

    # HTML 태그의 종료를 처리하고, 필요한 정보를 추출하는 로직을 구현
    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return

        if self._ignored_depth:
            return

        if tag == "title":
            self._in_title = False
        elif tag in {"h1", "h2", "h3"}:
            self._capture_heading = False
            heading_text = self._normalize_text(" ".join(self._heading_chunks))
            if heading_text and heading_text not in self.headings:
                self.headings.append(heading_text)
            self._heading_chunks = []

    # HTML 태그 사이의 텍스트 데이터를 처리하고, 필요한 정보를 추출하는 로직을 구현
    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return

        cleaned_text = self._normalize_text(data)
        if not cleaned_text:
            return

        if self._in_title:
            self.title_text = self._normalize_text(f"{self.title_text} {cleaned_text}")
        elif self._capture_heading:
            self._heading_chunks.append(cleaned_text)
        else:
            self.body_chunks.append(cleaned_text)

    # HTMLParser의 텍스트 정규화 유틸리티 메서드
    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(value.split())

    # srcset과 lazy-load 속성까지 포함해 대표 이미지를 최대한 많이 수집한다.
    def _collect_image_sources(self, attr_map: dict[str, str]) -> None:
        for attr_name in ("src", "data-src", "data-original", "data-lazy-src", "data-image"):
            source = attr_map.get(attr_name)
            if source:
                self._add_unique_image_url(self._resolve_url(source))

        for attr_name in ("srcset", "data-srcset"):
            source_set = attr_map.get(attr_name)
            if not source_set:
                continue
            for source in self._parse_srcset(source_set):
                self._add_unique_image_url(self._resolve_url(source))

    def _add_unique_image_url(self, image_url: str) -> None:
        if image_url and image_url not in self.image_urls:
            self.image_urls.append(image_url)

    def _resolve_url(self, url_value: str) -> str:
        cleaned_url = url_value.strip()
        if not cleaned_url:
            return ""
        if cleaned_url.startswith(("data:", "javascript:", "mailto:", "tel:")):
            return ""
        return urljoin(self.base_url, cleaned_url)

    @staticmethod
    def _parse_srcset(source_set: str) -> list[str]:
        sources: list[str] = []
        for candidate in source_set.split(","):
            source = candidate.strip().split(" ")[0]
            if source:
                sources.append(source)
        return sources


# 회사 웹사이트에서 주요 텍스트와 이미지 URL을 추출하는 간단한 크롤러
def fetch_company_page(url: str, timeout_seconds: int | None = None) -> CompanyPageSnapshot:
    timeout = timeout_seconds if timeout_seconds is not None else settings.company_crawl_timeout_seconds
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; WehomeVideoAgent/1.0)"})

    print(f"[CompanyIngest] Fetch started: {url} (timeout={timeout}s)", flush=True)
    started_at = time.monotonic()

    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        html_text = response.read().decode(charset, errors="replace")

    parser = _CompanyPageParser(url)
    parser.feed(html_text)

    body_text = parser._normalize_text(" ".join(parser.body_chunks))
    if settings.company_body_max_chars > 0:
        body_text = body_text[: settings.company_body_max_chars]
    elapsed_seconds = time.monotonic() - started_at
    print(f"[CompanyIngest] Fetch completed: {url} ({elapsed_seconds:.2f}s)", flush=True)

    return CompanyPageSnapshot(
        url=url,
        title=parser.title_text,
        meta_description=parser.meta_description,
        canonical_url=parser.canonical_url,
        og_title=parser.og_title,
        og_description=parser.og_description,
        og_image_url=parser.og_image_url,
        headings=parser.headings,
        body_text=body_text,
        image_urls=parser.image_urls,
    )


# 여러 페이지를 크롤링하고, 추출한 정보를 종합해 영상 기획용 프로필을 빌드하는 함수
def crawl_company_site(
    urls: list[str] | None = None,
    timeout_seconds: int | None = None,
    max_pages: int | None = None,
) -> list[CompanyPageSnapshot]:
    raw_source_urls = urls if urls is not None else list(settings.company_source_urls)
    source_urls = _dedupe_preserve_order(raw_source_urls)
    page_limit = max_pages if max_pages is not None else settings.company_max_pages

    snapshots: list[CompanyPageSnapshot] = []
    crawl_started_at = time.monotonic()
    print(f"[CompanyIngest] Crawl started: {min(len(source_urls), page_limit)} page(s)", flush=True)

    for url in source_urls[:page_limit]:
        page_started_at = time.monotonic()
        try:
            snapshot = fetch_company_page(url, timeout_seconds=timeout_seconds)
            snapshots.append(snapshot)
            page_elapsed = time.monotonic() - page_started_at
            print(f"[CompanyIngest] Page done: {url} ({page_elapsed:.2f}s)", flush=True)
        except Exception as exc:
            page_elapsed = time.monotonic() - page_started_at
            print(f"[CompanyIngest] Page failed: {url} ({page_elapsed:.2f}s) -> {exc}", flush=True)
            if settings.company_crawl_continue_on_error:
                continue
            raise

    crawl_elapsed = time.monotonic() - crawl_started_at
    if source_urls and not snapshots:
        raise RuntimeError("Company crawl finished without any successful pages.")

    print(f"[CompanyIngest] Crawl finished: {len(snapshots)} page(s) in {crawl_elapsed:.2f}s", flush=True)
    return snapshots


# 여러 페이지에서 추출한 정보를 종합해 영상 기획용 프로필을 빌드하는 함수
def build_company_profile(
    pages: list[CompanyPageSnapshot],
    brand_name: str | None = None,
    output_path: str | None = None,
) -> CompanyProfile:
    source_urls = _dedupe_preserve_order([page.canonical_url or page.url for page in pages])
    image_urls: list[str] = []
    summary_points: list[str] = []

    for page in pages:
        for image_url in page.image_urls:
            if image_url not in image_urls:
                image_urls.append(image_url)

        for text in [page.meta_description, page.og_title, page.og_description, *page.headings]:
            normalized_text = text.strip()
            if normalized_text and normalized_text not in summary_points:
                summary_points.append(normalized_text)

        if page.body_text and page.body_text not in summary_points:
            summary_points.append(page.body_text[:300])

    inferred_brand_name = brand_name or _infer_brand_name(pages)
    if not inferred_brand_name:
        inferred_brand_name = "Company Profile"

    profile = CompanyProfile(
        brand_name=inferred_brand_name,
        source_urls=source_urls,
        pages=[asdict(page) for page in pages],
        summary_points=summary_points[:10],
        image_urls=image_urls,
    )

    save_company_profile(profile, output_path=output_path)
    return profile


# 회사 웹사이트에서 크롤링한 결과를 다음 단계에서 재사용할 수 있도록 JSON 파일로 저장하는 함수
def save_company_profile(profile: CompanyProfile, output_path: str | None = None) -> str:
    base_path = output_path if output_path is not None else settings.company_profile_output_path
    target_path = _build_numbered_output_path(base_path)
    target_dir = os.path.dirname(target_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as file_handle:
        json.dump(asdict(profile), file_handle, ensure_ascii=False, indent=2)

    return target_path


def _build_numbered_output_path(base_path: str) -> str:
    target_dir = os.path.dirname(base_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    filename = os.path.basename(base_path)
    file_root, file_ext = os.path.splitext(filename)
    if not file_ext:
        file_ext = ".json"

    pattern = re.compile(rf"^{re.escape(file_root)}_(\d{{3}}){re.escape(file_ext)}$")
    existing_numbers: list[int] = []
    search_dir = target_dir or "."

    for entry_name in os.listdir(search_dir):
        match = pattern.match(entry_name)
        if match:
            existing_numbers.append(int(match.group(1)))

    next_number = (max(existing_numbers) + 1) if existing_numbers else 1
    return os.path.join(search_dir, f"{file_root}_{next_number:03d}{file_ext}")


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped_values: list[str] = []
    for value in values:
        normalized_value = value.strip()
        if normalized_value and normalized_value not in deduped_values:
            deduped_values.append(normalized_value)
    return deduped_values


# 회사 웹사이트에서 추출한 여러 페이지의 정보를 종합해 영상 기획용 프로필을 빌드할 때 브랜드명을 추론하는 간단한 유틸리티 함수
def _infer_brand_name(pages: list[CompanyPageSnapshot]) -> str:
    for page in pages:
        if page.title:
            return page.title.split("|")[0].strip()
        if page.og_title:
            return page.og_title.split("|")[0].strip()
        if page.headings:
            return page.headings[0]
    return ""
