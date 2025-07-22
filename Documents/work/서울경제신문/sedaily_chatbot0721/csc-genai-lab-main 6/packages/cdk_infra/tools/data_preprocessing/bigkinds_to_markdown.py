#!/usr/bin/env python3
"""
BigKinds 뉴스 데이터 수집 및 마크다운 변환 스크립트
- JSON → Markdown 변환
- Knowledge Base 형식으로 자동 변환
- S3 업로드 준비
"""

import os
import json
import requests
from datetime import datetime
from dateutil import parser, relativedelta
from dotenv import load_dotenv
from typing import Dict, List, Any
import argparse
import time

load_dotenv()

# BigKinds API 설정
API_URL = "https://tools.kinds.or.kr/search/news"
ACCESS_KEY = os.getenv("BIGKINDS_KEY")

CATEGORIES = {
    "정치": "001000000",
    "경제": "002000000",
    "사회": "003000000",
    "문화": "004000000",
    "국제": "005000000",
    "지역": "006000000",
    "스포츠": "007000000",
    "IT_과학": "008000000",
}

FIELDS = [
    "news_id", "title", "content", "byline", "publisher_name",
    "published_at", "provider_link_page",
    "category", "category_code", "year", "month"
]

def fetch_all_news(category_code: str, date_from: datetime, date_to: datetime) -> List[Dict]:
    """지정된 카테고리와 날짜 범위의 모든 뉴스를 가져옵니다."""
    all_docs = []
    offset = 0
    size = 10000
    
    while True:
        payload = {
            "access_key": ACCESS_KEY,
            "argument": {
                "query": "",
                "published_at": {
                    "from": date_from.strftime("%Y-%m-%dT00:00:00"),
                    "until": date_to.strftime("%Y-%m-%dT23:59:59")
                },
                "category": [category_code],
                "sort": {"date": "asc"},
                "return_from": offset,
                "return_size": size,
                "fields": FIELDS
            }
        }
        
        try:
            r = requests.post(API_URL, json=payload, timeout=30)
            r.raise_for_status()
            ret = r.json()["return_object"]
            batch = ret["documents"]
            
            if not batch:
                break
                
            all_docs.extend(batch)
            offset += len(batch)
            
            if offset >= ret["total_hits"]:
                break
                
            # API 속도 제한 대응
            time.sleep(0.5)
            
        except Exception as e:
            print(f"API 오류: {e}")
            break
    
    # URL 필드 정규화
    for doc in all_docs:
        doc["url"] = doc.pop("provider_link_page", None)
    
    return all_docs

def convert_to_markdown(articles: List[Dict], category: str, date: str) -> str:
    """JSON 기사 데이터를 마크다운 형식으로 변환합니다."""
    md_content = f"# {date} {category} 뉴스\n\n"
    md_content += f"**수집일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    md_content += f"**총 기사 수**: {len(articles)}개\n\n"
    md_content += "---\n\n"
    
    for idx, article in enumerate(articles, 1):
        # 기사 제목
        title = article.get("title", "제목 없음")
        md_content += f"### {idx}. {title}\n\n"
        
        # 메타데이터
        md_content += f"**발행일**: {article.get('published_at', 'N/A')}\n"
        md_content += f"**언론사**: {article.get('publisher_name', 'N/A')}\n"
        md_content += f"**기자**: {article.get('byline', 'N/A')}\n"
        md_content += f"**URL**: {article.get('url', 'N/A')}\n"
        md_content += f"**카테고리**: {category}\n\n"
        
        # 본문
        content = article.get("content", "내용 없음")
        # 긴 줄 처리 (마크다운 가독성)
        content = content.replace("\n", "\n\n")
        md_content += f"**내용**:\n{content}\n\n"
        
        md_content += "---\n\n"
    
    return md_content

def save_as_jsonl_for_knowledge_base(articles: List[Dict], output_path: str, category: str, date: str):
    """Knowledge Base용 JSONL 형식으로 저장합니다."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for article in articles:
            # Knowledge Base에 필요한 형식으로 변환
            kb_doc = {
                "chunk": article.get("content", ""),
                "title": article.get("title", ""),
                "date": date,
                "url": article.get("url", ""),
                "category": category,
                "publisher": article.get("publisher_name", ""),
                "byline": article.get("byline", ""),
                "article_id": article.get("news_id", ""),
                "metadata": {
                    "source": "BigKinds",
                    "collection_date": datetime.now().isoformat()
                }
            }
            f.write(json.dumps(kb_doc, ensure_ascii=False) + '\n')

def main():
    parser = argparse.ArgumentParser(description="BigKinds 뉴스 데이터 수집 및 변환")
    parser.add_argument("--start-date", default="2023-02-17", help="시작 날짜 (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2025-07-20", help="종료 날짜 (YYYY-MM-DD)")
    parser.add_argument("--output-format", choices=["json", "markdown", "jsonl", "all"], default="all", 
                       help="출력 형식 선택")
    parser.add_argument("--output-dir", default="output", help="출력 디렉토리")
    args = parser.parse_args()
    
    START_DATE = parser.parse(args.start_date)
    END_DATE = parser.parse(args.end_date)
    
    current = START_DATE
    while current <= END_DATE:
        day_start = current
        day_end = current
        y, m, d = day_start.year, day_start.month, day_start.day
        date_str = f"{y:04d}-{m:02d}-{d:02d}"
        
        for name, code in CATEGORIES.items():
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 수집 중: {date_str} / {name}")
            
            # 뉴스 수집
            docs = fetch_all_news(code, day_start, day_end)
            
            if not docs:
                print(f"  → 기사 없음")
                continue
                
            print(f"  → {len(docs)}개 기사 수집 완료")
            
            # 출력 폴더 생성
            folder = os.path.join(args.output_dir, f"{y:04d}", f"{m:02d}", f"{d:02d}")
            os.makedirs(folder, exist_ok=True)
            
            # JSON 저장
            if args.output_format in ["json", "all"]:
                json_path = os.path.join(folder, f"{name}.json")
                meta = {
                    "year": y, "month": m, "day": d,
                    "category": name,
                    "total_articles": len(docs),
                    "collection_date": datetime.now().isoformat(),
                    "date_range": {
                        "from": day_start.strftime("%Y-%m-%d"),
                        "until": day_end.strftime("%Y-%m-%d")
                    }
                }
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump({"metadata": meta, "articles": docs}, f, ensure_ascii=False, indent=2)
                print(f"  → JSON 저장: {json_path}")
            
            # Markdown 저장
            if args.output_format in ["markdown", "all"]:
                md_path = os.path.join(folder, f"{name}.md")
                md_content = convert_to_markdown(docs, name, date_str)
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                print(f"  → Markdown 저장: {md_path}")
            
            # JSONL 저장 (Knowledge Base용)
            if args.output_format in ["jsonl", "all"]:
                jsonl_path = os.path.join(folder, f"{name}.jsonl")
                save_as_jsonl_for_knowledge_base(docs, jsonl_path, name, date_str)
                print(f"  → JSONL 저장: {jsonl_path}")
        
        current += relativedelta.relativedelta(days=1)
    
    print("\n✅ 데이터 수집 및 변환 완료!")
    
    # S3 업로드 명령어 출력
    print("\n📤 S3 업로드 명령어:")
    print(f"aws s3 sync {args.output_dir}/ s3://seoul-economic-news-data-2025/bigkinds-data/ --exclude '*.json'")
    
    # Knowledge Base 정보
    print("\n🗄️ Knowledge Base 정보:")
    print("- Knowledge Base ID: PGQV3JXPET")
    print("- Data Source ID: W8DS8YQGZG")
    print("- S3 버킷: seoul-economic-news-data-2025")
    print("\n동기화 명령어:")
    print("aws bedrock-agent start-ingestion-job --knowledge-base-id PGQV3JXPET --data-source-id W8DS8YQGZG")

if __name__ == "__main__":
    main()