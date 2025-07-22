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
    BigKinds API를 사용하여 뉴스 기사를 가져옵니다.
    경제 관련 뉴스를 중심으로 수집합니다.
    """
    try:
        base_url = "https://www.bigkinds.or.kr/api/news/search.do"
        
        # 경제 관련 키워드
        keywords = [
            "경제", "증시", "주식", "부동산", "금융", "기업", "산업", 
            "투자", "수출", "수입", "GDP", "물가", "금리", "환율"
        ]
        
        all_articles = []
        
        for keyword in keywords:
            params = {
                'access_key': api_key,
                'argument': json.dumps({
                    'query': keyword,
                    'byLine': '',
                    'searchFilterType': 'detail',
                    'filterList': [],
                    'dateFilterType': 'select',
                    'startDate': start_date,
                    'endDate': end_date,
                    'categoryFilter': ['정치>정치일반', '경제>경제일반', '경제>증권', '경제>부동산'],
                    'categoryFilterType': 'include',
                    'sort': {'sortMethod': 'date', 'sortOrder': 'desc'},
                    'hilight': 200,
                    'returnFrom': 0,
                    'returnSize': 50,
                    'fields': ['byline', 'category', 'content', 'date', 'title', 'url']
                }),
                'kind': 'news'
            }
            
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('returnCode') == '200' and 'resultList' in data:
                articles = data['resultList']
                logger.info(f"Found {len(articles)} articles for keyword: {keyword}")
                
                for article in articles:
                    # 중복 제거를 위해 URL을 기준으로 확인
                    if not any(existing['url'] == article['url'] for existing in all_articles):
                        all_articles.append(article)
            
            # API 호출 제한을 위한 잠시 대기
            import time
            time.sleep(1)
        
        logger.info(f"Total unique articles collected: {len(all_articles)}")
        return all_articles
        
    except Exception as e:
        logger.error(f"Failed to fetch news from BigKinds: {str(e)}")
        return []

def save_articles_to_s3(articles: List[Dict[str, Any]]) -> int:
    """
    수집된 기사들을 Knowledge Base용 JSONL 형식으로 S3에 저장합니다.
    """
    try:
        processed_count = 0
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        for article in articles:
            try:
                # 기사 데이터를 Knowledge Base 형식으로 변환
                processed_article = process_article_for_knowledge_base(article)
                
                if processed_article:
                    # S3 키 생성 (날짜별로 구성)
                    article_id = str(uuid.uuid4())
                    s3_key = f"news-data/{current_date}/{article_id}.jsonl"
                    
                    # JSONL 형식으로 저장
                    jsonl_content = json.dumps(processed_article, ensure_ascii=False)
                    
                    s3_client.put_object(
                        Bucket=DATA_BUCKET_NAME,
                        Key=s3_key,
                        Body=jsonl_content.encode('utf-8'),
                        ContentType='application/json',
                        Metadata={
                            'source': 'bigkinds-api',
                            'collection_date': current_date,
                            'article_date': processed_article.get('date', ''),
                            'category': processed_article.get('category', '')
                        }
                    )
                    
                    processed_count += 1
                    logger.debug(f"Saved article to S3: {s3_key}")
                
            except Exception as e:
                logger.error(f"Failed to save individual article: {str(e)}")
                continue
        
        logger.info(f"Successfully saved {processed_count} articles to S3")
        return processed_count
        
    except Exception as e:
        logger.error(f"Failed to save articles to S3: {str(e)}")
        raise

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