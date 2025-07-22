#!/usr/bin/env python3
"""Markdown 뉴스 파일 → 기사 단위 청크 JSONL 변환기

사용법 예)
    python md_to_chunks.py \
        --input_dir ../../서울경제뉴스데이터_마크다운/2016/04/10 \
        --output out/2016_04_10_chunks.jsonl \
        --chunk_bytes 700

결과는 JSON Lines(.jsonl) 형식으로 저장되며, 각 행은 OpenSearch Bulk
API 의 _source 로 바로 넣을 수 있는 구조입니다.

필드 구조
----------
chunk           : str  – 본문 조각(임베딩 대상)
path            : str  – S3 상대 경로(연,월,일/파일명.md)
article_idx     : int  – 해당 파일 내 기사 번호(1 부터)
chunk_idx       : int  – 기사 내 청크 번호(1 부터)
title           : str
date            : str  – YYYY-MM-DD
url             : str
category        : str 또는 list
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Iterator, List, Dict

# --- 정규식 패턴 ---
TITLE_RE = re.compile(r"^###\s*\d+\.\s*(.+)$")
DATE_RE = re.compile(r"\*\*발행일:\*\*\s*([0-9T:\-+]+)")
URL_RE = re.compile(r"\*\*URL:\*\*\s*(https?://[^\s]+)")
CATEGORY_RE = re.compile(r"\*\*카테고리:\*\*\s*(.+)")


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

def find_articles(md_text: str) -> List[str]:
    """`---` 구분자로 기사 블록 나누기."""
    # 첫 메타데이터/헤더 부분은 제거하고 기사만 반환
    parts = md_text.split("\n---\n")
    return parts[1:] if len(parts) > 1 else []


def extract_metadata(article_md: str) -> Dict[str, str]:
    """기사 블록에서 메타데이터 추출"""
    meta = {}
    title_m = TITLE_RE.search(article_md)
    date_m = DATE_RE.search(article_md)
    url_m = URL_RE.search(article_md)
    cat_m = CATEGORY_RE.search(article_md)
    if title_m:
        meta["title"] = title_m.group(1).strip()
    if date_m:
        meta["date"] = date_m.group(1)[:10]  # YYYY-MM-DD
    if url_m:
        meta["url"] = url_m.group(1).strip()
    if cat_m:
        meta["category"] = cat_m.group(1).strip()
    return meta


def chunk_text(text: str, max_bytes: int = 700) -> List[str]:
    """대략 max_bytes 를 넘지 않도록 문단 단위 슬라이딩 윈도우.
    간단 로직: 공백/줄바꿈으로 split 후 누적.
    """
    words = text.split()
    chunks, current = [], []
    size = 0
    for w in words:
        size += len(w.encode()) + 1
        current.append(w)
        if size >= max_bytes:
            chunks.append(" ".join(current))
            current, size = [], 0
    if current:
        chunks.append(" ".join(current))
    return chunks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def iter_md_files(input_dir: Path) -> Iterator[Path]:
    for p in input_dir.rglob("*.md"):
        yield p


def process_file(md_path: Path, base_dir: Path, chunk_bytes: int) -> Iterator[dict]:
    rel_path = md_path.relative_to(base_dir)
    content = md_path.read_text(encoding="utf-8")
    for art_idx, article_md in enumerate(find_articles(content), 1):
        meta = extract_metadata(article_md)
        body_start = article_md.find("**내용:")
        body = article_md[body_start + 6:].strip() if body_start != -1 else article_md
        for c_idx, chunk in enumerate(chunk_text(body, chunk_bytes), 1):
            yield {
                "chunk": chunk,
                "path": str(rel_path),
                "article_idx": art_idx,
                "chunk_idx": c_idx,
                **meta,
            }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_dir", required=True, help="마크다운 루트 디렉터리")
    ap.add_argument("--output", required=True, help="출력 jsonl 파일 경로")
    ap.add_argument("--chunk_bytes", type=int, default=700)
    args = ap.parse_args()

    inp_root = Path(args.input_dir)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as fw:
        for md in iter_md_files(inp_root):
            for rec in process_file(md, inp_root, args.chunk_bytes):
                fw.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[완료] {out_path} 생성")


if __name__ == "__main__":
    main()