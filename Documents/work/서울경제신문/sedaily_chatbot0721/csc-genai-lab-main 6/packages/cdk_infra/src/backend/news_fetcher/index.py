import json
import logging
import os
import boto3
import requests
from datetime import datetime, timedelta
import uuid
from typing import Dict, List, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')
bedrock_agent = boto3.client('bedrock-agent')

BIGKINDS_API_SECRET_ARN = os.environ['BIGKINDS_API_SECRET_ARN']
DATA_BUCKET_NAME = os.environ['DATA_BUCKET_NAME']
KNOWLEDGE_BASE_ID = os.environ['KNOWLEDGE_BASE_ID']
DATA_SOURCE_ID = os.environ['DATA_SOURCE_ID']

def lambda_handler(event, context):
    """
    BigKinds API를 사용하여 최신 뉴스 데이터를 수집하고 
    S3에 저장한 후 Knowledge Base 동기화를 트리거합니다.
    """
    try:
        logger.info("Starting news data collection process")
        
        # BigKinds API 키 가져오기
        bigkinds_api_key = get_bigkinds_api_key()
        
        # 오늘부터 7일 전까지의 뉴스 데이터 수집
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        # BigKinds에서 뉴스 데이터 수집
        news_articles = fetch_bigkinds_news(
            api_key=bigkinds_api_key,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )
        
        if not news_articles:
            logger.info("No new articles found")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No new articles found',
                    'processed_count': 0
                })
            }
        
        # S3에 JSONL 형식으로 저장
        processed_count = save_articles_to_s3(news_articles)
        
        # Knowledge Base 동기화 시작
        sync_job_id = trigger_knowledge_base_sync()
        
        logger.info(f"Successfully processed {processed_count} articles")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'News data collection completed successfully',
                'processed_count': processed_count,
                'sync_job_id': sync_job_id,
                'timestamp': datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        logger.error(f"Error in news data collection: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'News data collection failed',
                'message': str(e)
            })
        }

def get_bigkinds_api_key() -> str:
    """Secrets Manager에서 BigKinds API 키를 가져옵니다."""
    try:
        response = secrets_client.get_secret_value(SecretId=BIGKINDS_API_SECRET_ARN)
        secret_data = json.loads(response['SecretString'])
        return secret_data['BIGKINDS_API_KEY']
    except Exception as e:
        logger.error(f"Failed to retrieve BigKinds API key: {str(e)}")
        raise

def fetch_bigkinds_news(api_key: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    BigKinds API를 사용하여 서울경제신문 뉴스를 수집합니다.
    """
    try:
        base_url = "https://tools.kinds.or.kr/search/news"
        
        categories = {
            "정치": "001000000",
            "경제": "002000000", 
            "사회": "003000000",
            "문화": "004000000",
            "국제": "005000000",
            "지역": "006000000",
            "스포츠": "007000000",
            "IT_과학": "008000000",
        }
        
        fields = [
            "news_id", "title", "content", "byline", "publisher_name",
            "published_at", "provider_link_page",
            "category", "category_code", "year", "month"
        ]
        
        all_articles = []
        
        for category_name, category_code in categories.items():
            offset = 0
            size = 1000
            
            while True:
                payload = {
                    "access_key": api_key,
                    "argument": {
                        "query": "",
                        "published_at": {
                            "from": f"{start_date}T00:00:00",
                            "until": f"{end_date}T23:59:59"
                        },
                        "provider": [
                            "서울경제"  # 서울경제신문만 수집
                        ],
                        "category": [category_code],
                        "sort": {"date": "desc"},
                        "return_from": offset,
                        "return_size": size,
                        "fields": fields
                    }
                }
                
                response = requests.post(base_url, json=payload, timeout=30)
                response.raise_for_status()
                
                ret = response.json()["return_object"]
                batch = ret["documents"]
                
                if not batch:
                    break
                    
                # URL 필드 정규화
                for doc in batch:
                    doc["url"] = doc.pop("provider_link_page", None)
                    doc["category"] = category_name
                
                all_articles.extend(batch)
                offset += len(batch)
                
                if offset >= ret["total_hits"]:
                    break
                
                # API 호출 제한 대응
                import time
                time.sleep(0.5)
            
            logger.info(f"Collected {len([a for a in all_articles if a.get('category') == category_name])} articles for {category_name}")
        
        logger.info(f"Total articles collected: {len(all_articles)}")
        return all_articles
        
    except Exception as e:
        logger.error(f"Failed to fetch news from BigKinds: {str(e)}")
        return []

def save_articles_to_s3(articles: List[Dict[str, Any]]) -> int:
    """
    수집된 기사들을 Knowledge Base용 마크다운 형식으로 S3에 저장합니다.
    """
    try:
        processed_count = 0
        current_date = datetime.now()
        date_str = current_date.strftime('%Y-%m-%d')
        
        # 카테고리별로 기사 그룹화
        articles_by_category = {}
        for article in articles:
            category = article.get('category', '기타')
            if category not in articles_by_category:
                articles_by_category[category] = []
            articles_by_category[category].append(article)
        
        # 각 카테고리별로 마크다운 파일 생성
        for category, category_articles in articles_by_category.items():
            try:
                # 마크다운 내용 생성
                md_content = f"# {date_str} {category} 뉴스\n\n"
                md_content += f"**수집일시**: {current_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                md_content += f"**총 기사 수**: {len(category_articles)}개\n\n"
                md_content += "---\n\n"
                
                for idx, article in enumerate(category_articles, 1):
                    # 기사를 마크다운 형식으로 변환
                    md_article = convert_article_to_markdown(article, idx)
                    md_content += md_article
                
                # S3에 마크다운 파일로 저장
                year = current_date.strftime('%Y')
                month = current_date.strftime('%m')
                day = current_date.strftime('%d')
                
                # 파일 경로: news-data-md/YYYY/MM/DD/카테고리.md (S3 구조와 일치)
                s3_key = f"news-data-md/{year}/{month}/{day}/{category}.md"
                
                s3_client.put_object(
                    Bucket=DATA_BUCKET_NAME,
                    Key=s3_key,
                    Body=md_content.encode('utf-8'),
                    ContentType='text/markdown; charset=utf-8',
                    Metadata={
                        'source': 'bigkinds-api',
                        'collection_date': date_str,
                        'category': category,
                        'article_count': str(len(category_articles))
                    }
                )
                
                processed_count += len(category_articles)
                logger.info(f"Saved {len(category_articles)} articles to S3: {s3_key}")
                
                # JSONL 형식도 함께 저장 (Knowledge Base 호환성)
                jsonl_key = f"news-data-md/{year}/{month}/{day}/{category}.jsonl"
                jsonl_content = ""
                
                for article in category_articles:
                    kb_doc = {
                        "chunk": article.get("content", ""),
                        "title": article.get("title", ""),
                        "date": format_date(article.get('date', '')),
                        "url": article.get("url", ""),
                        "category": category,
                        "publisher": article.get("byline", ""),
                        "metadata": {
                            "source": "BigKinds",
                            "collection_timestamp": current_date.isoformat()
                        }
                    }
                    jsonl_content += json.dumps(kb_doc, ensure_ascii=False) + "\n"
                
                s3_client.put_object(
                    Bucket=DATA_BUCKET_NAME,
                    Key=jsonl_key,
                    Body=jsonl_content.encode('utf-8'),
                    ContentType='application/x-ndjson; charset=utf-8'
                )
                
            except Exception as e:
                logger.error(f"Failed to save articles for category {category}: {str(e)}")
                continue
        
        logger.info(f"Successfully saved {processed_count} articles to S3")
        return processed_count
        
    except Exception as e:
        logger.error(f"Failed to save articles to S3: {str(e)}")
        raise

def convert_article_to_markdown(article: Dict[str, Any], idx: int) -> str:
    """개별 기사를 마크다운 형식으로 변환합니다."""
    md = f"### {idx}. {article.get('title', '제목 없음')}\n\n"
    
    # 메타데이터
    md += f"**발행일**: {format_date(article.get('date', ''))}\n"
    md += f"**URL**: {article.get('url', 'N/A')}\n"
    md += f"**카테고리**: {article.get('category', 'N/A')}\n"
    
    if article.get('byline'):
        md += f"**기자/출처**: {article['byline']}\n"
    
    md += "\n**내용**:\n"
    
    # 본문 내용
    content = article.get('content', '내용 없음')
    # 긴 줄 처리
    content = content.replace('\n', '\n\n')
    md += f"{content}\n\n"
    
    md += "---\n\n"
    
    return md

def process_article_for_knowledge_base(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    BigKinds 기사 데이터를 Knowledge Base에 적합한 형식으로 변환합니다.
    """
    try:
        # 기사 내용 정제
        content = article.get('content', '').strip()
        title = article.get('title', '').strip()
        
        if not content or not title:
            return None
        
        # 텍스트 청킹 (700바이트 단위)
        chunks = chunk_text(content, max_bytes=700)
        
        processed_article = {
            'title': title,
            'content': content,
            'chunks': chunks,
            'date': format_date(article.get('date', '')),
            'url': article.get('url', ''),
            'category': article.get('category', ''),
            'byline': article.get('byline', ''),
            'source': 'BigKinds API',
            'collection_timestamp': datetime.now().isoformat(),
            'chunk_count': len(chunks)
        }
        
        return processed_article
        
    except Exception as e:
        logger.error(f"Failed to process article: {str(e)}")
        return None

def chunk_text(text: str, max_bytes: int = 700) -> List[str]:
    """텍스트를 지정된 바이트 크기로 청킹합니다."""
    if not text:
        return []
    
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0
    
    for word in words:
        word_size = len(word.encode('utf-8'))
        
        if current_size + word_size + 1 > max_bytes and current_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_size = word_size
        else:
            current_chunk.append(word)
            current_size += word_size + 1
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

def format_date(date_str: str) -> str:
    """날짜 형식을 YYYY-MM-DD로 표준화합니다."""
    try:
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        
        # BigKinds 날짜 형식 처리
        if 'T' in date_str:
            date_part = date_str.split('T')[0]
        else:
            date_part = date_str
        
        # 날짜 형식 검증
        datetime.strptime(date_part, '%Y-%m-%d')
        return date_part
        
    except ValueError:
        logger.warning(f"Invalid date format: {date_str}, using current date")
        return datetime.now().strftime('%Y-%m-%d')

def trigger_knowledge_base_sync() -> str:
    """Knowledge Base 데이터 소스 동기화를 시작합니다."""
    try:
        response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            dataSourceId=DATA_SOURCE_ID,
            description=f"Automated sync triggered at {datetime.now().isoformat()}"
        )
        
        job_id = response['ingestionJob']['ingestionJobId']
        logger.info(f"Started Knowledge Base sync job: {job_id}")
        return job_id
        
    except Exception as e:
        logger.error(f"Failed to trigger Knowledge Base sync: {str(e)}")
        # 동기화 실패는 치명적이지 않으므로 예외를 발생시키지 않음
        return "sync_failed"