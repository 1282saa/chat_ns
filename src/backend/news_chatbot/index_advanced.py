"""
Advanced News Chatbot Handler

AI 기반 질문 확장, 개선된 청킹, 각주 인용 시스템이 포함된 고급 뉴스 챗봇입니다.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple

import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, CORSConfig
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

# 환경 변수 설정
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# AWS Lambda Powertools 초기화
logger = Logger(service="news-chatbot", level=LOG_LEVEL)
tracer = Tracer(service="news-chatbot")

# CORS 설정
cors_config = CORSConfig(
    allow_origin="*",
    allow_headers=["content-type", "x-amz-date", "authorization", "x-api-key", "x-amz-security-token"],
    max_age=86400,
)

app = APIGatewayRestResolver(cors=cors_config)

# AWS 클라이언트 초기화
bedrock_runtime = boto3.client("bedrock-runtime")
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
s3_client = boto3.client("s3")


class ChatbotError(Exception):
    """챗봇 관련 사용자 정의 예외"""
    pass


@tracer.capture_method
def expand_query_with_ai(original_query: str) -> str:
    """
    AI를 사용하여 검색 질문을 확장합니다.
    
    Args:
        original_query: 원본 질문
        
    Returns:
        AI가 확장한 검색 질문
    """
    try:
        prompt = f"""다음 질문을 뉴스 검색에 더 적합하도록 확장해주세요. 
원본 질문: "{original_query}"

확장 규칙:
1. 기업명이 있으면 관련 계열사, 주요 사업 분야 추가
2. 경제 용어가 있으면 관련 키워드 추가  
3. 최대 3-4개의 관련 키워드만 추가
4. 한국 경제/기업 뉴스 맥락에서 확장

확장된 검색어만 출력하세요 (설명 없이):"""

        response = bedrock_runtime.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ]
            })
        )
        
        result = json.loads(response['body'].read())
        expanded_query = result['content'][0]['text'].strip()
        
        logger.info(f"AI expanded query: '{original_query}' -> '{expanded_query}'")
        return expanded_query
        
    except Exception as e:
        logger.warning(f"Failed to expand query with AI: {str(e)}")
        return original_query


class BedrockService:
    """Bedrock Knowledge Base와 상호작용하는 서비스 클래스"""
    
    def __init__(self, knowledge_base_id: str):
        self.knowledge_base_id = knowledge_base_id
        self.client = bedrock_agent_runtime
    
    @tracer.capture_method
    def retrieve_and_generate(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Bedrock Knowledge Base에서 정보를 검색하고 답변을 생성합니다.
        
        Args:
            query: 사용자 질문
            max_results: 검색할 최대 결과 수
            
        Returns:
            생성된 답변과 메타데이터를 포함한 딕셔너리
        """
        try:
            # AI를 사용하여 질문 확장
            expanded_query = expand_query_with_ai(query)
            
            logger.info(f"Querying knowledge base with expanded query: {expanded_query}")
            
            # 개선된 검색 설정으로 요청
            response = self.client.retrieve_and_generate(
                input={
                    "text": expanded_query
                },
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": self.knowledge_base_id,
                        "modelArn": "arn:aws:bedrock:ap-northeast-2::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": max_results,
                                "overrideSearchType": "HYBRID"  # 하이브리드 검색 활성화
                            }
                        },
                        "generationConfiguration": {
                            "promptTemplate": {
                                "textPromptTemplate": """다음 뉴스 기사들을 참고하여 질문에 답변해주세요.

질문: $query$

뉴스 기사:
$search_results$

답변 작성 규칙:
1. 제공된 뉴스 기사의 정보만 사용하여 답변하세요
2. 중요한 정보나 수치를 언급할 때는 반드시 출처를 명시하세요
3. 각 문장 끝에 [1], [2] 형태의 각주 번호를 추가하세요
4. 정확하고 객관적인 정보만 제공하세요
5. 추측이나 개인적 의견은 포함하지 마세요

답변:"""
                            }
                        }
                    }
                }
            )
            
            logger.info("Successfully retrieved and generated response")
            return response
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", "Unknown error")
            logger.error(f"Bedrock API error: {error_code} - {error_message}")
            raise ChatbotError(f"지식 기반 검색 중 오류가 발생했습니다: {error_message}")
        
        except Exception as e:
            logger.error(f"Unexpected error in retrieve_and_generate: {str(e)}")
            raise ChatbotError("답변 생성 중 예상치 못한 오류가 발생했습니다")


def validate_request_body(body: Dict[str, Any]) -> str:
    """요청 본문의 유효성을 검사하고 질문을 추출합니다."""
    if not isinstance(body, dict):
        raise ChatbotError("요청 본문은 JSON 객체여야 합니다")
    
    question = body.get("question", "").strip()
    if not question:
        raise ChatbotError("질문(question) 필드가 필요합니다")
    
    if len(question) > 1000:
        raise ChatbotError("질문은 1000자를 초과할 수 없습니다")
    
    return question


def extract_best_matching_article(s3_uri: str, original_query: str) -> Dict[str, str]:
    """
    S3 파일에서 검색어와 가장 관련성 높은 기사를 찾아 메타데이터를 추출합니다.
    
    개선된 청킹 전략:
    - 각 기사를 완전한 단위로 처리 (제목 + 메타데이터 + 본문)
    - 기사별로 관련성 점수 계산
    - 가장 관련성 높은 기사의 메타데이터 반환
    """
    metadata = {
        "title": "",
        "date": "",
        "author": "",
        "media": "",
        "url": "",
        "relevance_score": 0.0,
        "article_content": ""
    }
    
    try:
        if not s3_uri.startswith("s3://"):
            return metadata
            
        s3_path = s3_uri[5:]
        bucket, key = s3_path.split("/", 1)
        
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        
        # 기사별로 분할 (개선된 청킹)
        articles = re.split(r'\n---\n', content)
        
        best_article = None
        best_score = 0.0
        
        for article in articles:
            if "### " in article and "**발행일:**" in article:
                # 관련성 점수 계산
                score = calculate_relevance_score(article, original_query)
                
                if score > best_score:
                    best_score = score
                    best_article = article
        
        if best_article and best_score > 0.1:  # 최소 관련성 임계값
            # 메타데이터 추출
            title_match = re.search(r'###\s*\d+\.\s*(.+?)(?:\n|$)', best_article)
            if title_match:
                metadata["title"] = title_match.group(1).strip()
            
            date_match = re.search(r'\*\*발행일:\*\*\s*([^\n]+)', best_article)
            if date_match:
                date_str = date_match.group(1).strip()
                try:
                    dt = datetime.fromisoformat(date_str.replace('T00:00:00.000+09:00', ''))
                    metadata["date"] = dt.strftime('%Y년 %m월 %d일')
                except:
                    metadata["date"] = date_str
            
            author_match = re.search(r'\*\*기자:\*\*\s*([^\n]+)', best_article)
            if author_match:
                metadata["author"] = author_match.group(1).strip()
            
            media_match = re.search(r'\*\*언론사:\*\*\s*([^\n]+)', best_article)
            if media_match:
                metadata["media"] = media_match.group(1).strip()
            
            url_match = re.search(r'\*\*URL:\*\*\s*([^\n]+)', best_article)
            if url_match:
                metadata["url"] = url_match.group(1).strip()
            
            # 기사 내용 일부 저장 (각주용)
            content_match = re.search(r'\*\*내용:\*\*\s*\n\n(.{1,200})', best_article, re.DOTALL)
            if content_match:
                metadata["article_content"] = content_match.group(1).strip()
            
            metadata["relevance_score"] = best_score
        
        logger.info(f"Best article: title={metadata['title'][:50]}..., score={best_score:.3f}")
        
    except Exception as e:
        logger.warning(f"Failed to extract article from S3 {s3_uri}: {str(e)}")
    
    return metadata


def calculate_relevance_score(article_content: str, query: str) -> float:
    """
    개선된 관련성 점수 계산 알고리즘
    
    점수 계산 기준:
    1. 제목에서 키워드 발견: 높은 점수 (0.5점)
    2. 메타데이터(카테고리)에서 발견: 중간 점수 (0.3점)  
    3. 본문에서 발견: 기본 점수 (0.1점)
    4. 정확한 매칭: 보너스 점수 (0.2점)
    """
    if not query or not article_content:
        return 0.0
    
    query_lower = query.lower()
    content_lower = article_content.lower()
    
    score = 0.0
    query_words = [word for word in query_lower.split() if len(word) > 1]
    
    if not query_words:
        return 0.0
    
    for word in query_words:
        # 제목에서 발견 (높은 점수)
        title_section = content_lower[:content_lower.find('**발행일:**')] if '**발행일:**' in content_lower else content_lower[:200]
        if word in title_section:
            score += 0.5
        
        # 카테고리에서 발견 (중간 점수)
        elif '**카테고리:**' in content_lower:
            category_start = content_lower.find('**카테고리:**')
            category_end = content_lower.find('\n', category_start)
            if category_end > category_start and word in content_lower[category_start:category_end]:
                score += 0.3
        
        # 본문에서 발견 (기본 점수)
        elif word in content_lower:
            score += 0.1
    
    # 정확한 매칭 보너스
    if query_lower in content_lower:
        score += 0.2
    
    # 정규화 (0.0 ~ 1.0)
    normalized_score = min(score / len(query_words), 1.0)
    
    return normalized_score


def add_footnotes_to_answer(answer: str, sources: List[Dict]) -> str:
    """
    답변에 각주 번호를 추가합니다.
    
    Args:
        answer: 원본 답변
        sources: 출처 목록
        
    Returns:
        각주가 추가된 답변
    """
    if not sources:
        return answer
    
    # 이미 [숫자] 형태의 각주가 있는지 확인
    footnote_pattern = r'\[\d+\]'
    if re.search(footnote_pattern, answer):
        return answer  # 이미 각주가 있으면 그대로 반환
    
    # 문장 단위로 분할하여 각주 추가
    sentences = re.split(r'(?<=[.!?])\s+', answer)
    
    footnoted_answer = ""
    footnote_num = 1
    
    for i, sentence in enumerate(sentences):
        footnoted_answer += sentence
        
        # 각 문장마다 각주 추가 (최대 출처 수만큼)
        if footnote_num <= len(sources) and sentence.strip():
            footnoted_answer += f" [{footnote_num}]"
            footnote_num += 1
        
        if i < len(sentences) - 1:
            footnoted_answer += " "
    
    return footnoted_answer


@app.post("/chat")
@tracer.capture_method
def handle_chat():
    """챗봇 대화 요청을 처리합니다."""
    try:
        request_body = app.current_event.json_body
        question = validate_request_body(request_body)
        
        logger.info(f"Processing chat request: {question}")
        
        # Bedrock Knowledge Base를 통한 답변 생성
        bedrock_service = BedrockService(KNOWLEDGE_BASE_ID)
        response = bedrock_service.retrieve_and_generate(question)
        
        answer = response.get("output", {}).get("text", "답변을 생성할 수 없습니다")
        citations = response.get("citations", [])
        
        logger.info(f"Retrieved {len(citations)} citations")
        
        # 출처 정보 추출 (개선된 청킹 적용)
        sources = []
        for citation in citations:
            for reference in citation.get("retrievedReferences", []):
                location = reference.get("location", {})
                s3_location = location.get("s3Location", {})
                s3_uri = s3_location.get("uri", "")
                
                if s3_uri:
                    article_metadata = extract_best_matching_article(s3_uri, question)
                    
                    # 관련성이 높은 기사만 포함
                    if article_metadata["relevance_score"] > 0.1:
                        source_info = {
                            "location": location,
                            "title": article_metadata["title"],
                            "date": article_metadata["date"],
                            "author": article_metadata["author"],
                            "media": article_metadata["media"],
                            "url": article_metadata["url"],
                            "relevance_score": article_metadata["relevance_score"],
                            "preview": article_metadata["article_content"]
                        }
                        sources.append(source_info)
        
        # 관련성 점수로 정렬
        sources.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # 상위 5개만 선택
        top_sources = sources[:5]
        
        # 답변에 각주 추가
        footnoted_answer = add_footnotes_to_answer(answer, top_sources)
        
        result = {
            "answer": footnoted_answer,
            "sources": top_sources,
            "question": question,
            "timestamp": response.get("sessionId", ""),
            "search_quality": {
                "total_found": len(sources),
                "relevant_sources": len(top_sources),
                "avg_relevance": sum(s.get("relevance_score", 0) for s in top_sources) / len(top_sources) if top_sources else 0
            }
        }
        
        logger.info(f"Generated response with {len(top_sources)} relevant sources")
        return result
        
    except ChatbotError as e:
        logger.warning(f"Chatbot error: {str(e)}")
        return {
            "error": str(e),
            "type": "validation_error"
        }, 400
        
    except Exception as e:
        logger.error(f"Unexpected error in handle_chat: {str(e)}")
        return {
            "error": "서버 내부 오류가 발생했습니다",
            "type": "internal_error"
        }, 500


@app.get("/health")
@tracer.capture_method
def health_check():
    """헬스 체크 엔드포인트"""
    try:
        if not KNOWLEDGE_BASE_ID:
            return {
                "status": "unhealthy",
                "message": "Knowledge Base ID가 설정되지 않았습니다"
            }, 500
        
        return {
            "status": "healthy",
            "service": "news-chatbot-advanced",
            "knowledge_base_id": KNOWLEDGE_BASE_ID,
            "version": "3.0.0",
            "features": [
                "AI-powered query expansion",
                "Improved chunking strategy", 
                "Footnote citations",
                "Relevance scoring"
            ]
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }, 500


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
def handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Lambda 함수의 메인 핸들러"""
    logger.info("Processing request", extra={"event": event})
    
    try:
        return app.resolve(event, context)
    except Exception as e:
        logger.error(f"Unhandled error in lambda handler: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "error": "서버 내부 오류가 발생했습니다",
                "type": "internal_error"
            }, ensure_ascii=False)
        }
