"""
News Chatbot Handler with Debug Logging

디버그 로깅이 추가된 버전입니다.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

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

# Bedrock Agent Runtime 클라이언트 초기화
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")


class ChatbotError(Exception):
    """챗봇 관련 사용자 정의 예외"""
    pass


class BedrockService:
    """Bedrock Knowledge Base와 상호작용하는 서비스 클래스"""
    
    def __init__(self, knowledge_base_id: str):
        self.knowledge_base_id = knowledge_base_id
        self.client = bedrock_agent_runtime
    
    @tracer.capture_method
    def retrieve_and_generate(self, query: str, max_results: int = 3) -> Dict[str, Any]:
        """
        Bedrock Knowledge Base에서 정보를 검색하고 답변을 생성합니다.
        
        Args:
            query: 사용자 질문
            max_results: 검색할 최대 결과 수
            
        Returns:
            생성된 답변과 메타데이터를 포함한 딕셔너리
        """
        try:
            logger.info(f"Querying knowledge base with: {query}")
            
            response = self.client.retrieve_and_generate(
                input={
                    "text": query
                },
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": self.knowledge_base_id,
                        "modelArn": "arn:aws:bedrock:ap-northeast-2::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": max_results
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
    """
    요청 본문의 유효성을 검사하고 질문을 추출합니다.
    
    Args:
        body: API 요청 본문
        
    Returns:
        검증된 사용자 질문
        
    Raises:
        ChatbotError: 요청이 유효하지 않은 경우
    """
    if not isinstance(body, dict):
        raise ChatbotError("요청 본문은 JSON 객체여야 합니다")
    
    question = body.get("question", "").strip()
    if not question:
        raise ChatbotError("질문(question) 필드가 필요합니다")
    
    if len(question) > 1000:
        raise ChatbotError("질문은 1000자를 초과할 수 없습니다")
    
    return question


def extract_article_metadata(content: str) -> Dict[str, str]:
    """
    뉴스 기사 내용에서 메타데이터를 추출합니다.
    
    Args:
        content: 뉴스 기사 내용 텍스트
        
    Returns:
        추출된 메타데이터 딕셔너리 (title, date, author, media, url)
    """
    metadata = {
        "title": "",
        "date": "",
        "author": "",
        "media": "",
        "url": ""
    }
    
    try:
        # 디버그: content의 일부를 로그에 출력
        logger.info(f"Content preview (first 500 chars): {content[:500]}")
        
        # 제목 추출 (### 다음에 오는 제목)
        title_match = re.search(r'###\s*\d+\.\s*(.+?)(?:\n|$)', content)
        if title_match:
            metadata["title"] = title_match.group(1).strip()
            logger.info(f"Extracted title: {metadata['title']}")
        
        # 발행일 추출
        date_match = re.search(r'\*\*발행일:\*\*\s*([^\n]+)', content)
        if date_match:
            date_str = date_match.group(1).strip()
            # ISO 날짜를 한국어 형식으로 변환
            try:
                dt = datetime.fromisoformat(date_str.replace('T00:00:00.000+09:00', ''))
                metadata["date"] = dt.strftime('%Y년 %m월 %d일')
            except:
                metadata["date"] = date_str
            logger.info(f"Extracted date: {metadata['date']}")
        
        # 기자 추출
        author_match = re.search(r'\*\*기자:\*\*\s*([^\n]+)', content)
        if author_match:
            metadata["author"] = author_match.group(1).strip()
            logger.info(f"Extracted author: {metadata['author']}")
        
        # 언론사 추출
        media_match = re.search(r'\*\*언론사:\*\*\s*([^\n]+)', content)
        if media_match:
            metadata["media"] = media_match.group(1).strip()
            logger.info(f"Extracted media: {metadata['media']}")
        
        # URL 추출
        url_match = re.search(r'\*\*URL:\*\*\s*([^\n]+)', content)
        if url_match:
            metadata["url"] = url_match.group(1).strip()
            logger.info(f"Extracted URL: {metadata['url']}")
            
    except Exception as e:
        logger.warning(f"Failed to extract metadata from content: {str(e)}")
    
    return metadata


@app.post("/chat")
@tracer.capture_method
def handle_chat():
    """
    챗봇 대화 요청을 처리합니다.
    """
    try:
        # 요청 본문 파싱 및 검증
        request_body = app.current_event.json_body
        question = validate_request_body(request_body)
        
        logger.info(f"Processing chat request for question: {question[:100]}...")
        
        # Bedrock Knowledge Base를 통한 답변 생성
        bedrock_service = BedrockService(KNOWLEDGE_BASE_ID)
        response = bedrock_service.retrieve_and_generate(question)
        
        # 응답 데이터 구성
        answer = response.get("output", {}).get("text", "답변을 생성할 수 없습니다")
        citations = response.get("citations", [])
        
        logger.info(f"Retrieved {len(citations)} citations")
        
        # 출처 정보 추출 및 메타데이터 파싱
        sources = []
        for citation_idx, citation in enumerate(citations):
            logger.info(f"Processing citation {citation_idx + 1}")
            for ref_idx, reference in enumerate(citation.get("retrievedReferences", [])):
                content = reference.get("content", {}).get("text", "")
                location = reference.get("location", {})
                
                logger.info(f"Reference {ref_idx + 1} content length: {len(content)}")
                
                # 메타데이터 추출
                metadata = extract_article_metadata(content)
                
                source_info = {
                    "location": location,
                    "title": metadata["title"],
                    "date": metadata["date"],
                    "author": metadata["author"],
                    "media": metadata["media"],
                    "url": metadata["url"]
                }
                sources.append(source_info)
        
        result = {
            "answer": answer,
            "sources": sources[:5],  # 최대 5개 소스만 반환
            "question": question,
            "timestamp": response.get("sessionId", "")
        }
        
        logger.info("Successfully generated chat response")
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
    """
    헬스 체크 엔드포인트
    
    Returns:
        서비스 상태 정보
    """
    try:
        # Knowledge Base ID 존재 여부 확인
        if not KNOWLEDGE_BASE_ID:
            return {
                "status": "unhealthy",
                "message": "Knowledge Base ID가 설정되지 않았습니다"
            }, 500
        
        return {
            "status": "healthy",
            "service": "news-chatbot",
            "knowledge_base_id": KNOWLEDGE_BASE_ID,
            "version": "1.0.0"
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
    """
    Lambda 함수의 메인 핸들러
    
    Args:
        event: API Gateway 이벤트
        context: Lambda 실행 컨텍스트
        
    Returns:
        API Gateway 응답 형식의 딕셔너리
    """
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
