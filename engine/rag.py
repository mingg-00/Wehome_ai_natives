"""위홈 RAG (Retrieval-Augmented Generation) 엔진.

knowledge/ 폴더의 마크다운 문서를 벡터 DB에 인덱싱하고,
콘텐츠 생성 시 관련 문서를 검색해 LLM 프롬프트에 주입합니다.

사용:
    from engine import rag
    context = rag.retrieve("에어비앤비 대비 위홈 장점", top_k=3)
    # → 관련 문서 청크 텍스트 반환
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

# ── 경로 설정 ────────────────────────────────────────────────────────────
_BASE = Path(__file__).parent.parent
_KNOWLEDGE_DIR = _BASE / "knowledge"
_DB_DIR = _BASE / "output" / "chroma_db"

# ── ChromaDB 초기화 ──────────────────────────────────────────────────────
_client: Optional[chromadb.PersistentClient] = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    _DB_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(_DB_DIR))

    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-3-small",
        )
    else:
        ef = embedding_functions.DefaultEmbeddingFunction()

    _collection = _client.get_or_create_collection(
        name="wehome_knowledge",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


# ── 문서 청킹 ────────────────────────────────────────────────────────────
def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    """문단 단위로 청킹 (overlap 포함)."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > chunk_size and current:
            chunks.append(current.strip())
            # overlap: 이전 청크 마지막 부분 재포함
            current = current[-overlap:] + "\n" + para
        else:
            current = (current + "\n" + para).strip() if current else para
    if current:
        chunks.append(current.strip())
    return chunks


def _doc_id(source: str, idx: int) -> str:
    h = hashlib.md5(source.encode()).hexdigest()[:8]
    return f"{h}_{idx}"


# ── 인덱싱 ──────────────────────────────────────────────────────────────
def index_all(force: bool = False) -> int:
    """knowledge/ 폴더의 .md 파일을 모두 인덱싱. 변경된 파일만 재인덱싱."""
    col = _get_collection()
    total = 0

    for md_file in sorted(_KNOWLEDGE_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        file_hash = hashlib.md5(text.encode()).hexdigest()

        # 이미 같은 버전이 인덱싱돼 있으면 스킵
        existing = col.get(where={"source": md_file.name}, limit=1)
        if not force and existing["ids"] and existing["metadatas"]:
            stored_hash = existing["metadatas"][0].get("hash", "")
            if stored_hash == file_hash:
                continue

        # 기존 항목 삭제 후 재인덱싱
        old = col.get(where={"source": md_file.name})
        if old["ids"]:
            col.delete(ids=old["ids"])

        chunks = _chunk_text(text)
        if not chunks:
            continue

        col.add(
            ids=[_doc_id(md_file.name, i) for i in range(len(chunks))],
            documents=chunks,
            metadatas=[{"source": md_file.name, "hash": file_hash, "chunk": i}
                       for i in range(len(chunks))],
        )
        total += len(chunks)
        print(f"[RAG] 인덱싱: {md_file.name} ({len(chunks)} 청크)")

    return total


def index_text(text: str, source_name: str) -> int:
    """단일 텍스트를 knowledge base에 추가 (동적 추가용)."""
    col = _get_collection()
    file_hash = hashlib.md5(text.encode()).hexdigest()

    old = col.get(where={"source": source_name})
    if old["ids"]:
        col.delete(ids=old["ids"])

    chunks = _chunk_text(text)
    if not chunks:
        return 0

    col.add(
        ids=[_doc_id(source_name, i) for i in range(len(chunks))],
        documents=chunks,
        metadatas=[{"source": source_name, "hash": file_hash, "chunk": i}
                   for i in range(len(chunks))],
    )
    return len(chunks)


# ── 검색 ────────────────────────────────────────────────────────────────
def retrieve(query: str, top_k: int = 3) -> str:
    """쿼리와 관련된 위홈 지식을 검색해 문자열로 반환."""
    col = _get_collection()

    # 인덱싱된 문서가 없으면 자동 인덱싱
    if col.count() == 0:
        indexed = index_all()
        if indexed == 0:
            return ""

    results = col.query(query_texts=[query], n_results=min(top_k, col.count()))
    docs = results.get("documents", [[]])[0]
    if not docs:
        return ""

    return "\n\n---\n\n".join(docs)


def retrieve_as_context(query: str, top_k: int = 3) -> str:
    """LLM 프롬프트에 바로 삽입할 수 있는 형태로 반환."""
    content = retrieve(query, top_k)
    if not content:
        return ""
    return f"[위홈 지식 베이스]\n{content}\n[/위홈 지식 베이스]"


def list_sources() -> list[str]:
    """인덱싱된 문서 소스 목록 반환."""
    col = _get_collection()
    if col.count() == 0:
        return []
    result = col.get()
    sources = list({m["source"] for m in result["metadatas"]})
    return sorted(sources)
