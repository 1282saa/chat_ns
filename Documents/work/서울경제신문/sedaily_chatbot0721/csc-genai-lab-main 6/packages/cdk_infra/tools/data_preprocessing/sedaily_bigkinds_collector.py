#!/usr/bin/env python3
"""
서울경제신문 전용 BigKinds 뉴스 수집기
- 매일 10분마다 실행되는 자동화 스크립트
- JSON -> Markdown 변환
- S3 업로드 (s3://seoul-economic-news-data-2025/news-data-md/)
- 서울경제신문만 수집
"""

import os
import json
import requests
import boto3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Dict, List, Any
import argparse

load_dotenv()

# BigKinds API 설정 (원래 구조 유지)
API_URL = "https://tools.kinds.or.kr/search/news"
ACCESS_KEY = os.getenv("BIGKINDS_KEY", "254bec69-1c13-470f-904a-c4bc9e46cc80")

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

# S3 설정
S3_BUCKET = "seoul-economic-news-data-2025"
S3_PREFIX = "news-data-md"

def fetch_all(category_code, date_from, date_to):
    """원래 함수 구조 유지 - 서울경제 전용으로 수정"""
    docs, all_docs = [], []
    offset, size = 0, 10000
    
    while True:
        payload = {
            "access_key": ACCESS_KEY,
            "argument": {
                "query": "",
                "published_at": {
                    "from": date_from.strftime("%Y-%m-%dT00:00:00"),
                    "until": date_to.strftime("%Y-%m-%dT23:59:59")
                },
                "provider": [
                    "서울경제"  # 서울경제신문만 수집
                ],
                "category": [category_code],
                "sort": {"date": "desc"},
                "return_from": offset,
                "return_size": size,
                "fields": FIELDS
            }
        }
        
        try:
            r = requests.post(API_URL, json=payload)
            r.raise_for_status()
            ret = r.json()["return_object"]
            batch = ret["documents"]
            
            if not batch:
                break
                
            all_docs.extend(batch)
            offset += len(batch)
            
            if offset >= ret["total_hits"]:
                break
                
        except Exception as e:
            print(f"API 오류: {e}")
            break
    
    # URL 필드 정규화 (원래 구조 유지)
    for d in all_docs:
        d["url"] = d.pop("provider_link_page", None)
    
    return all_docs

def convert_to_markdown(articles: List[Dict], category: str, date: str) -> str:
    """JSON 기사를 마크다운 형식으로 변환"""
    if not articles:
        return f"# {date} {category} 뉴스\n\n수집된 기사가 없습니다.\n"
    
    md_content = f"# {date} {category} 뉴스\n\n"
    md_content += f"**수집일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    md_content += f"**총 기사 수**: {len(articles)}개\n"
    md_content += f"**출처**: 서울경제신문\n\n"
    md_content += "---\n\n"
    
    for idx, article in enumerate(articles, 1):
        title = article.get("title", "제목 없음").strip()
        md_content += f"### {idx}. {title}\n\n"
        
        # 메타데이터
        published_at = article.get("published_at", "")
        if published_at:
            try:
                pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                formatted_date = pub_date.strftime('%Y-%m-%d %H:%M')
            except:
                formatted_date = published_at
        else:
            formatted_date = "N/A"
            
        md_content += f"**발행일**: {formatted_date}\n"
        md_content += f"**URL**: {article.get('url', 'N/A')}\n"
        md_content += f"**카테고리**: {category}\n"
        
        byline = article.get("byline", "")
        if byline:
            md_content += f"**기자**: {byline}\n"
        
        md_content += "\n**내용**:\n"
        
        content = article.get("content", "내용 없음").strip()
        if content:
            content = content.replace('\\n', '\n').replace('\n\n\n', '\n\n')
            md_content += f"{content}\n\n"
        else:
            md_content += "내용이 제공되지 않았습니다.\n\n"
        
        md_content += "---\n\n"
    
    return md_content

def save_to_local_and_s3(content: str, category: str, date_str: str, local_only: bool = False):
    """로컬 저장 및 S3 업로드 (덮어쓰기 방식)"""
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    year = date_obj.strftime('%Y')
    month = date_obj.strftime('%m')
    day = date_obj.strftime('%d')
    
    # 로컬 저장
    folder = os.path.join("output", year, month, day)
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, f"{category}.md")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"로컬 저장: {file_path}")
    
    # S3 업로드 (덮어쓰기)
    if not local_only:
        try:
            s3_client = boto3.client('s3')
            s3_key = f"{S3_PREFIX}/{year}/{month}/{day}/{category}.md"
            
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType='text/markdown; charset=utf-8',
                Metadata={
                    'source': 'sedaily-bigkinds',
                    'collection_date': datetime.now().isoformat(),
                    'category': category,
                    'date': date_str
                }
            )
            print(f"S3 업로드: s3://{S3_BUCKET}/{s3_key}")
            
        except Exception as e:
            print(f"S3 업로드 실패: {e}")

def collect_daily_news(target_date: datetime = None, local_only: bool = False):
    """지정된 날짜의 뉴스를 수집 (원래 구조 기반)"""
    if target_date is None:
        target_date = datetime.now() - timedelta(days=1)
    
    date_str = target_date.strftime('%Y-%m-%d')
    print(f"{date_str} 서울경제 뉴스 수집 시작")
    
    total_articles = 0
    
    # 원래 구조와 동일한 방식으로 수집
    for name, code in CATEGORIES.items():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 수집 중: {date_str} / {name}")
        
        # fetch_all 함수 사용 (원래 구조 유지)
        docs = fetch_all(code, target_date, target_date)
        
        if docs:
            print(f"  -> {len(docs)}개 기사 수집 완료")
            total_articles += len(docs)
        else:
            print(f"  -> 기사 없음")
        
        # 마크다운 변환
        md_content = convert_to_markdown(docs, name, date_str)
        
        # 저장 (덮어쓰기)
        save_to_local_and_s3(md_content, name, date_str, local_only)
    
    print(f"수집 완료: 총 {total_articles}개 기사")
    return total_articles

def main():
    parser = argparse.ArgumentParser(description="서울경제신문 BigKinds 뉴스 수집기")
    parser.add_argument("--date", help="수집할 날짜 (YYYY-MM-DD, 기본값: 어제)")
    parser.add_argument("--local-only", action="store_true", help="로컬 저장만")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (오늘 뉴스)")
    args = parser.parse_args()
    
    if args.test:
        target_date = datetime.now()
        print("테스트 모드: 오늘 뉴스 수집")
    elif args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d')
    else:
        target_date = datetime.now() - timedelta(days=1)
    
    if not ACCESS_KEY:
        print("BigKinds API 키가 설정되지 않았습니다!")
        print("환경변수 BIGKINDS_KEY를 설정해주세요.")
        return
    
    try:
        collect_daily_news(target_date, args.local_only)
    except KeyboardInterrupt:
        print("사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    main()