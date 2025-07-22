"""
Simple News Chatbot Handler

AWS Lambda Powertools 의존성 없이 기본 라이브러리만 사용하는 버전입니다.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple
from difflib import SequenceMatcher
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
import requests

# Perplexity API settings
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY")
PPLX_URL = "https://api.perplexity.ai/chat/completions"

# 환경 변수 설정
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# AWS 클라이언트 초기화
bedrock_runtime = boto3.client("bedrock-runtime")
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
s3_client = boto3.client("s3")


class ChatbotError(Exception):
    """챗봇 관련 사용자 정의 예외"""
    pass


def expand_query_with_ai(original_query: str) -> str:
    """AI를 사용하여 검색 질문을 확장합니다."""
    try:
        current_year = datetime.now().year
        prompt = f"""다음 질문을 뉴스 검색에 더 적합하도록 확장해주세요. 
원본 질문: "{original_query}"

확장 규칙:
1. 기업명이 있으면 관련 계열사, 주요 사업 분야 추가
2. 경제 용어가 있으면 관련 키워드 추가  
3. 최대 3-4개의 관련 키워드만 추가
4. 한국 경제/기업 뉴스 맥락에서 확장
5. 중요: 현재 년도는 {current_year}년입니다. 최신 이슈인 경우 {current_year}년 또는 {current_year-1}년 키워드 추가

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


# -----------------------
# Helper: detect if external search needed
# -----------------------

DATE_KEYWORDS = [
    # 일(day) 단위
    "그제", "그제이틀 전", "그저께", "어제", "어저께", "전일", "금일", "오늘", "당일", "내일", "익일", "모레", "글피",
    "5일 전", "3일 전", "2일 전",

    # 주(week) 단위
    "지난주", "지난 주", "지지난주", "지지난 주", "지난 한 주", "지난 1주일", "금주", "이번 주", "이번주",
    "이번 한 주", "이번 1주일", "다음주", "다음 주", "차주", "다음 한 주", "다음 1주일",
    "2주 전", "3주 전", "4주 전",

    # 월(month) 단위
    "지난달", "지난 달", "지난 한 달", "지난 1개월", "지지난달", "지지난 달",
    "금월", "이번 달", "이번달", "이번 한 달", "이번 1개월",
    "다음달", "다음 달", "차월", "다음 한 달", "다음 1개월",
    "2개월 전", "3개월 전", "6개월 전",

    # 분기(quarter) 단위
    "지난 분기", "지난분기", "이번 분기", "이번분기", "다음 분기", "다음분기",

    # 반기(half-year)
    "상반기", "하반기", "작년 상반기", "지난 상반기", "작년 하반기", "지난 하반기",

    # 연(year) 단위
    "작년", "지난 해", "지난해", "지난 한 해", "지난 1년",
    "재작년", "2년 전", "3년 전", "5년 전", "10년 전",
    "금년", "금년도", "올해", "올 해", "2025년", "2024년",
    "내년", "다음 해", "다음해", "차년", "내년도",
    "2년 후", "3년 후",

    # 느슨한/비정형 표현
    "얼마 전", "얼마 지나지 않아", "조만간", "머지않아", "곧", "빠른 시일 내",
    "바로 전", "바로 후"
]



def needs_external_search(question: str) -> bool:
    """간단한 휴리스틱으로 날짜·시사성 키워드가 포함되어 있으면 True"""
    lower_q = question.lower()
    if any(k.replace(" ", "") in lower_q for k in [kw.replace(" ", "") for kw in DATE_KEYWORDS]):
        return True
    # 너무 모호하거나 짧은 질문도 외부 검색(예: '무슨 일이 있었어?')
    if len(question.strip()) <= 4:
        return True
    return False


# -----------------------
# Helper: typo detection & Perplexity-based spell-fix
# -----------------------

def is_typo(question: str) -> bool:
    """간단 휴리스틱: 자음/모음 단독·영문 난독·편집거리로 오타 여부 판단"""
    # 한글 자음/모음만 2글자 이상 연속 → 오타 가능성
    if re.search(r"[ㄱ-ㅎㅏ-ㅣ]{2,}", question):
        return True
    # 영문 연속 4자 이상(한국어 맥락에서 흔치 않음)
    if re.search(r"[a-zA-Z]{4,}", question):
        return True
    # 사전 주요 키워드와 편집거리 확인 (간단 샘플)
    vocab = ["삼성전자", "금리", "환율", "부동산", "주가", "인플레이션"]
    for w in vocab:
        if SequenceMatcher(None, w, question).ratio() > 0.8:
            return False
    return False  # 보수적으로 False 반환 (심각 오타만 True)


def perplexity_spellfix(question: str) -> Tuple[str, str]:
    """Perplexity로 오타 교정·키워드 추출"""
    prompt = (
        "다음 문장을 한국어로 올바르게 교정한 뒤 JSON 형태로만 반환하세요.\n"
        "포맷: {\"corrected\":\"...\", \"keywords\":[\"...\"]}\n"
        f"문장: \"{question}\""
    )
    resp = query_perplexity(prompt, max_tokens=200)
    try:
        data = json.loads(resp)
        corrected = data.get("corrected", question)
        kws = ", ".join(data.get("keywords", []))
        return corrected, f"오타 교정 키워드: {kws}"
    except Exception as err:
        logger.warning(f"Spellfix JSON parse error: {err} – raw: {resp[:100]}")
        raise ChatbotError("Perplexity spellfix 실패")


# -----------------------
# Helper: hard question refine
# -----------------------

def perplexity_refine(question: str) -> Tuple[str, str]:
    """Perplexity로 날짜·시사성 질문 의도 보강"""
    current_year = datetime.now().year
    current_date = datetime.now().strftime('%Y년 %m월 %d일')
    
    prompt = (
        f"현재 날짜: {current_date}\n"
        f"사용자 질문을 한국 뉴스 검색에 적합하도록 정제하세요.\n"
        "상대적 날짜('어제', '오늘', '최근' 등)는 구체적 날짜나 년도로 변환하세요.\n"
        f"최신 이슈의 경우 {current_year}년 키워드를 포함하세요.\n"
        "JSON만 반환: {\"refined_query\":\"...\", \"summary\":\"...150자 내\", \"suggested_years\":[\"2024\", \"2025\"]} \n"
        f"질문: {question}"
    )
    resp = query_perplexity(prompt, max_tokens=300)
    try:
        data = json.loads(resp)
        refined_query = data.get("refined_query", question)
        summary = data.get("summary", "")
        years = data.get("suggested_years", [])
        
        # 연도 키워드를 refined_query에 추가
        if years:
            year_keywords = " ".join(years)
            refined_query = f"{refined_query} {year_keywords}"
            
        return refined_query, summary
    except Exception as err:
        logger.warning(f"Refine JSON parse error: {err} – raw: {resp[:100]}")
        raise ChatbotError("Perplexity refine 실패")


def orchestrated_news_search(query: str, max_retries: int = 3) -> Dict[str, Any]:
    """오케스트레이션 기반 뉴스 검색 - 단계별 분석 및 재시도 로직"""
    
    current_date = datetime.now().strftime('%Y년 %m월 %d일')
    current_year = datetime.now().year
    
    # Step 1: 질문 분석 및 계획 수립
    analysis_prompt = f"""현재 날짜: {current_date}

다음 사용자 질문을 분석하고 검색 계획을 수립하세요.

사용자 질문: "{query}"

다음 형식으로 JSON 응답:
{{
    "user_goal": "사용자가 원하는 것",
    "time_context": "질문의 시간적 맥락 (예: 2025년 6월, 최근, 과거 등)",
    "target_year_range": ["2024", "2025"],
    "key_entities": ["핵심 키워드들"],
    "search_strategy": "검색 전략 설명",
    "expected_article_timeframe": "기대하는 기사 시간대"
}}"""

    try:
        analysis_response = bedrock_runtime.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": analysis_prompt}]
            })
        )
        
        analysis_result = json.loads(analysis_response['body'].read())
        analysis_text = analysis_result['content'][0]['text'].strip()
        
        # JSON 추출
        analysis_data = json.loads(analysis_text)
        logger.info(f"Query analysis: {analysis_data}")
        
    except Exception as e:
        logger.warning(f"Analysis failed: {e}")
        analysis_data = {
            "user_goal": query,
            "target_year_range": [str(current_year), str(current_year-1)],
            "key_entities": [query],
            "search_strategy": "basic search"
        }

    # Step 2: 검색 시도 (최대 3회 재시도)
    for attempt in range(max_retries):
        logger.info(f"Search attempt {attempt + 1}/{max_retries}")
        
        # 시도별 검색 쿼리 생성
        if attempt == 0:
            # 첫 시도: 연도 + 핵심 키워드
            search_query = f"{' '.join(analysis_data.get('key_entities', [query]))} {' '.join(analysis_data.get('target_year_range', []))}"
        elif attempt == 1:
            # 두 번째 시도: 키워드만
            search_query = ' '.join(analysis_data.get('key_entities', [query]))
        else:
            # 마지막 시도: 원본 질문
            search_query = query
            
        logger.info(f"Attempt {attempt + 1} search query: {search_query}")
        
        # Bedrock 검색 실행
        search_result = execute_bedrock_search(search_query, analysis_data)
        
        # 결과 평가
        if evaluate_search_results(search_result, analysis_data, query):
            logger.info(f"Search succeeded on attempt {attempt + 1}")
            return search_result
        else:
            logger.warning(f"Search attempt {attempt + 1} failed quality check")
    
    # 모든 시도 실패 시 Perplexity 폴백
    logger.warning("All search attempts failed, using Perplexity fallback")
    return perplexity_fallback_search(query)


def execute_bedrock_search(search_query: str, analysis_data: Dict) -> Dict[str, Any]:
    """Bedrock Knowledge Base 검색 실행"""
    try:
        # 검색 실행
        retrieve_response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": search_query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": 5,
                    "overrideSearchType": "HYBRID"
                }
            }
        )
        
        retrieval_results = retrieve_response.get('retrievalResults', [])
        
        if not retrieval_results:
            raise ChatbotError("No search results found")
            
        return generate_orchestrated_response(search_query, retrieval_results, analysis_data)
        
    except Exception as e:
        logger.error(f"Bedrock search failed: {e}")
        raise ChatbotError(f"검색 실행 실패: {str(e)}")


def evaluate_search_results(search_result: Dict, analysis_data: Dict, original_query: str) -> bool:
    """검색 결과의 품질을 평가"""
    try:
        sources = search_result.get('sources', [])
        if not sources:
            return False
            
        # 날짜 관련성 체크
        target_years = analysis_data.get('target_year_range', [])
        if target_years:
            relevant_articles = 0
            for source in sources:
                source_date = source.get('date', '')
                if any(year in source_date for year in target_years):
                    relevant_articles += 1
            
            # 최소 60% 이상이 관련 년도여야 함 (기준 상향)
            relevance_ratio = relevant_articles / len(sources)
            logger.info(f"Date relevance ratio: {relevance_ratio:.2f} for years {target_years}")
            if relevance_ratio < 0.6:
                logger.warning(f"Low date relevance: {relevance_ratio:.2f}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Result evaluation failed: {e}")
        return False


def generate_orchestrated_response(query: str, retrieval_results: List, analysis_data: Dict) -> Dict[str, Any]:
    """오케스트레이션된 응답 생성"""
    # 날짜 필터링 적용된 기사 선별
    target_years = analysis_data.get('target_year_range', [])
    filtered_results = []
    
    for result in retrieval_results[:10]:  # 더 많은 결과에서 필터링
        # S3 URI에서 메타데이터 추출하여 날짜 확인
        s3_location = result.get('location', {}).get('s3Location', {})
        s3_uri = s3_location.get('uri', '')
        
        if s3_uri:
            try:
                content = result.get('content', {}).get('text', '')
                metadata = find_best_matching_article(s3_uri, content)
                article_date = metadata.get("date", "") if metadata else ""
                
                # 날짜가 타겟 년도와 매치되는지 확인
                if target_years and article_date:
                    date_match = any(year in article_date for year in target_years)
                    if date_match:
                        filtered_results.append(result)
                        logger.info(f"✅ Orchestration: Included article from {article_date}")
                    else:
                        logger.info(f"🚫 Orchestration: Filtered out article from {article_date}")
                else:
                    # 날짜 정보가 없으면 포함 (안전한 기본값)
                    filtered_results.append(result)
                    
            except Exception as e:
                logger.warning(f"Error filtering article by date: {e}")
                filtered_results.append(result)  # 에러 시 포함
        else:
            filtered_results.append(result)  # S3 URI가 없으면 포함
        
        if len(filtered_results) >= 5:  # 최대 5개만 사용
            break
    
    # 필터링 후 결과가 너무 적으면 원본 결과 사용
    if len(filtered_results) < 2 and len(retrieval_results) > 2:
        logger.warning(f"Orchestration: Date filtering left only {len(filtered_results)} articles, using original results")
        filtered_results = retrieval_results[:5]
    
    # 기사들을 번호로 포맷
    formatted_articles = []
    for i, result in enumerate(filtered_results[:5], 1):
        content = result.get('content', {}).get('text', '')
        formatted_articles.append(f"[기사 {i}]\n{content}")
    
    articles_text = '\n\n'.join(formatted_articles)
    
    # 향상된 프롬프트
    enhanced_prompt = f"""질문 분석 결과:
- 사용자 목표: {analysis_data.get('user_goal', '정보 검색')}
- 시간적 맥락: {analysis_data.get('time_context', '일반적')}
- 핵심 엔티티: {', '.join(analysis_data.get('key_entities', []))}

사용자 질문: {query}

검색된 뉴스 기사들:
{articles_text}

**중요 지침:**
1. 사용자의 구체적인 시간적 맥락을 고려하여 답변
2. 질문과 관련성이 높은 기사만 선별하여 인용
3. 날짜가 맞지 않는 기사는 제외하고 설명
4. 각주는 [1], [2], [3], [4], [5] 순서로만 사용

**각주 규칙:**
- 첫 번째로 인용하는 기사: [1]
- 두 번째로 인용하는 기사: [2]
- 세 번째로 인용하는 기사: [3]
- 네 번째로 인용하는 기사: [4]
- 다섯 번째로 인용하는 기사: [5]

답변 작성:"""

    # AI 응답 생성
    ai_response = bedrock_runtime.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": enhanced_prompt}]
        })
    )
    
    result = json.loads(ai_response['body'].read())
    answer = result['content'][0]['text'].strip()
    
    # 응답 구조 생성
    response = {
        "output": {"text": answer},
        "citations": [{
            "generatedResponsePart": {
                "textResponsePart": {
                    "span": {"start": 0, "end": len(answer)},
                    "text": answer
                }
            },
            "retrievedReferences": []
        }],
        "sessionId": f"orchestrated-{datetime.now().isoformat()}"
    }
    
    # 날짜 필터링된 결과만 참조로 추가
    for retrieval_result in filtered_results:
        reference = {
            "content": {"text": retrieval_result.get('content', {}).get('text', '')},
            "location": retrieval_result.get('location', {}),
            "metadata": retrieval_result.get('metadata', {})
        }
        response['citations'][0]["retrievedReferences"].append(reference)
    
    return response


def perplexity_fallback_search(query: str) -> Dict[str, Any]:
    """Perplexity를 사용한 폴백 검색"""
    try:
        current_date = datetime.now().strftime('%Y년 %m월 %d일')
        fallback_prompt = f"""현재 날짜: {current_date}

"{query}"에 대한 정보를 찾아 한국어로 답변해주세요.
최신 정보를 우선적으로 참조하고, 구체적인 날짜와 출처를 포함해주세요."""

        pplx_response = query_perplexity(fallback_prompt, max_tokens=500)
        
        return {
            "output": {"text": pplx_response},
            "citations": [],
            "sessionId": f"perplexity-{datetime.now().isoformat()}"
        }
        
    except Exception as e:
        logger.error(f"Perplexity fallback failed: {e}")
        raise ChatbotError("모든 검색 방법이 실패했습니다")


def retrieve_and_generate_with_references(query: str, max_results: int = 10, extra_context: str = "") -> Dict[str, Any]:
    """Bedrock Knowledge Base에서 정보를 검색하고 답변을 생성합니다. References도 함께 반환합니다."""
    try:
        # AI를 사용하여 질문 확장
        expanded_query = expand_query_with_ai(query)
        
        logger.info(f"Querying knowledge base with expanded query: {expanded_query}")
        
        # 1. retrieve API로 정확히 5개 기사 검색
        retrieve_response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={
                "text": expanded_query
            },
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": 5,  # 정확히 5개
                    "overrideSearchType": "HYBRID"
                }
            }
        )
        
        retrieval_results = retrieve_response.get('retrievalResults', [])
        logger.info(f"Retrieved {len(retrieval_results)} results from retrieve API")
        
        if not retrieval_results:
            raise ChatbotError("관련 뉴스를 찾을 수 없습니다")
        
        # 2. 검색된 기사들을 명시적으로 번호를 매겨서 포맷
        formatted_articles = []
        for i, result in enumerate(retrieval_results[:5], 1):  # 최대 5개만 사용
            content = result.get('content', {}).get('text', '')
            formatted_articles.append(f"[기사 {i}]\n{content}")
        
        articles_text = '\n\n'.join(formatted_articles)
        
        # 3. 직접 AI 모델에 질문 전송 (retrieveAndGenerate 대신)

        context_block = f"\n\n추가 참고 자료 (실시간 검색):\n{extra_context}\n" if extra_context else ""

        prompt = f"""사용자 질문에 맞는 뉴스 기사를 분석하고 요약 답변을 작성해주세요.

사용자 질문: {query}

{context_block}

검색된 뉴스 기사들:
{articles_text}

**작업 순서:**
1. 각 기사의 제목, 날짜를 확인하여 사용자 질문과 관련성 검토
2. 질문에 답변할 수 있는 핵심 정보가 있는 기사들을 선별
3. 선별된 기사들에서 인용할 문장들을 추출
4. 추출된 문장들을 바탕으로 간결한 답변 작성
5. 인용한 문장 뒤에 반드시 각주 번호 추가

**각주 규칙 (매우 중요):**
- 첫 번째로 인용하는 기사: [1]
- 두 번째로 인용하는 기사: [2]
- 세 번째로 인용하는 기사: [3]
- 네 번째로 인용하는 기사: [4]
- 다섯 번째로 인용하는 기사: [5]
- 반드시 [1]부터 시작해서 순차적으로 사용
- [6], [7], [8] 등 6번 이상의 숫자는 절대 사용 금지
- 같은 기사를 여러 번 인용할 때도 같은 번호 사용

**답변 작성 지침:**
- 2~4줄의 간결한 답변
- 구체적 정보 필수: 인명, 날짜, 기관명, 수치
- 인용한 문장 끝에 반드시 각주 표시
- 객관적 사실만 기반으로 작성

답변 작성:"""

        # AI 모델 직접 호출
        ai_response = bedrock_runtime.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ]
            })
        )
        
        result = json.loads(ai_response['body'].read())
        answer = result['content'][0]['text'].strip()
        
        # 4. 응답 구조 생성 (retrieveAndGenerate와 호환되도록)
        combined_response = {
            "output": {
                "text": answer
            },
            "citations": [{
                "generatedResponsePart": {
                    "textResponsePart": {
                        "span": {"start": 0, "end": len(answer)},
                        "text": answer
                    }
                },
                "retrievedReferences": []
            }],
            "sessionId": f"manual-{datetime.now().isoformat()}"
        }
        
        # retrieve 결과를 citations에 추가
        for retrieval_result in retrieval_results:
            reference = {
                "content": {
                    "text": retrieval_result.get('content', {}).get('text', '')
                },
                "location": retrieval_result.get('location', {}),
                "metadata": retrieval_result.get('metadata', {})
            }
            combined_response['citations'][0]["retrievedReferences"].append(reference)
        
        logger.info("Successfully retrieved and generated response with manual AI call")
        logger.info(f"Generated answer: {answer[:200]}...")
        
        return combined_response
        
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", "Unknown error")
        logger.error(f"Bedrock API error: {error_code} - {error_message}")
        raise ChatbotError(f"지식 기반 검색 중 오류가 발생했습니다: {error_message}")
    
    except Exception as e:
        logger.error(f"Unexpected error in retrieve_and_generate_with_references: {str(e)}")
        raise ChatbotError("답변 생성 중 예상치 못한 오류가 발생했습니다")


def query_perplexity(question: str, max_tokens: int = 512) -> str:
    """Fallback to Perplexity AI when Knowledge Base returns no result"""
    if not PERPLEXITY_API_KEY:
        raise ChatbotError("Perplexity API key not configured")

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "pplx-70b-online",  # 최신 온라인 모델
        "messages": [{"role": "user", "content": question}],
        "max_tokens": max_tokens,
    }

    try:
        resp = requests.post(PPLX_URL, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "답변을 찾지 못했습니다.")
            .strip()
        )
    except Exception as err:
        logger.error(f"Perplexity API error: {err}")
        raise ChatbotError("Perplexity API 호출 실패")


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


def extract_metadata_from_s3(s3_uri: str) -> Dict[str, str]:
    """S3 URI에서 원본 .md 파일을 읽어 메타데이터를 추출합니다."""
    metadata = {
        "title": "",
        "date": "",
        "author": "",
        "media": "서울경제",
        "url": ""
    }
    
    try:
        # S3 URI 파싱 (s3://bucket-name/path/to/file.md)
        parsed_uri = urlparse(s3_uri)
        bucket_name = parsed_uri.netloc
        object_key = parsed_uri.path.lstrip('/')
        
        logger.info(f"Reading S3 file: bucket={bucket_name}, key={object_key}")
        
        # S3에서 파일 읽기
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        content = response['Body'].read().decode('utf-8')
        
        # .md 파일에서 기사들을 분리 (--- 구분자 사용)
        articles = content.split('\n---\n')
        
        # 첫 번째 실제 기사에서 메타데이터 추출 (헤더 부분 제외)
        if len(articles) > 1:
            first_article = articles[1]  # 첫 번째 기사
            
            # 제목 추출 - ### 숫자. 제목 패턴
            title_match = re.search(r'###\s*\d+\.\s*(.+?)(?:\n|$)', first_article)
            if title_match:
                metadata["title"] = title_match.group(1).strip()
            
            # 발행일 추출
            date_match = re.search(r'\*\*발행일:\*\*\s*([^\n]+)', first_article)
            if date_match:
                date_str = date_match.group(1).strip()
                # ISO 날짜를 한국어 형식으로 변환
                try:
                    # 2016-04-10T00:00:00.000+09:00 형식 처리
                    if 'T' in date_str:
                        dt = datetime.fromisoformat(date_str.replace('T00:00:00.000+09:00', ''))
                        metadata["date"] = dt.strftime('%Y년 %m월 %d일')
                    else:
                        metadata["date"] = date_str
                except:
                    metadata["date"] = date_str
            
            # 기자 추출
            author_match = re.search(r'\*\*기자:\*\*\s*([^\n]+)', first_article)
            if author_match:
                metadata["author"] = author_match.group(1).strip()
            
            # 언론사 추출
            media_match = re.search(r'\*\*언론사:\*\*\s*([^\n]+)', first_article)
            if media_match:
                metadata["media"] = media_match.group(1).strip()
            
            # URL 추출
            url_match = re.search(r'\*\*URL:\*\*\s*([^\n\s]+)', first_article)
            if url_match:
                metadata["url"] = url_match.group(1).strip()
            
            logger.info(f"Extracted metadata from S3: {metadata}")
        
    except Exception as e:
        logger.warning(f"Failed to extract metadata from S3 {s3_uri}: {str(e)}")
    
    return metadata


def find_best_matching_article(s3_uri: str, query_chunk: str) -> Dict[str, str]:
    """S3 파일에서 쿼리와 가장 관련성 높은 기사를 찾아 메타데이터를 추출합니다."""
    try:
        # S3 URI 파싱
        parsed_uri = urlparse(s3_uri)
        bucket_name = parsed_uri.netloc
        object_key = parsed_uri.path.lstrip('/')
        
        # S3에서 파일 읽기
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        content = response['Body'].read().decode('utf-8')
        
        # .md 파일에서 기사들을 분리
        articles = content.split('\n---\n')
        
        best_metadata = None
        max_relevance = 0
        
        # 각 기사에서 관련성 검사
        for i, article in enumerate(articles[1:], 1):  # 첫 번째는 헤더이므로 제외
            # 제목 추출
            title_match = re.search(r'###\s*\d+\.\s*(.+?)(?:\n|$)', article)
            title = title_match.group(1).strip() if title_match else ""
            
            # 기사 본문에서 쿼리 청크와의 관련성 계산
            relevance = 0
            query_words = set(query_chunk.lower().split())
            article_words = set(article.lower().split())
            
            # 단어 매칭으로 간단한 관련성 계산
            common_words = query_words.intersection(article_words)
            if query_words:
                relevance = len(common_words) / len(query_words)
            
            # 제목에 쿼리 키워드가 포함되면 가중치 추가
            if any(word in title.lower() for word in query_words):
                relevance += 0.3
            
            logger.info(f"Article {i} relevance: {relevance:.3f}, title: {title[:50]}...")
            
            if relevance > max_relevance:
                max_relevance = relevance
                
                # 해당 기사의 메타데이터 추출
                metadata = {
                    "title": title,
                    "date": "",
                    "author": "",
                    "media": "서울경제",
                    "url": ""
                }
                
                # 발행일 추출
                date_match = re.search(r'\*\*발행일:\*\*\s*([^\n]+)', article)
                if date_match:
                    date_str = date_match.group(1).strip()
                    try:
                        if 'T' in date_str:
                            dt = datetime.fromisoformat(date_str.replace('T00:00:00.000+09:00', ''))
                            metadata["date"] = dt.strftime('%Y년 %m월 %d일')
                        else:
                            metadata["date"] = date_str
                    except:
                        metadata["date"] = date_str
                
                # 기자 추출
                author_match = re.search(r'\*\*기자:\*\*\s*([^\n]+)', article)
                if author_match:
                    metadata["author"] = author_match.group(1).strip()
                
                # 언론사 추출
                media_match = re.search(r'\*\*언론사:\*\*\s*([^\n]+)', article)
                if media_match:
                    metadata["media"] = media_match.group(1).strip()
                
                # URL 추출
                url_match = re.search(r'\*\*URL:\*\*\s*([^\n\s]+)', article)
                if url_match:
                    metadata["url"] = url_match.group(1).strip()
                
                best_metadata = metadata
        
        logger.info(f"Best matching article metadata: {best_metadata}")
        return best_metadata or extract_metadata_from_s3(s3_uri)
        
    except Exception as e:
        logger.warning(f"Failed to find best matching article: {str(e)}")
        return extract_metadata_from_s3(s3_uri)


def handle_chat(event: Dict[str, Any]) -> Dict[str, Any]:
    """챗봇 대화 요청을 처리합니다."""
    try:
        # API Gateway 이벤트에서 본문 추출
        if 'body' in event:
            if isinstance(event['body'], str):
                request_body = json.loads(event['body'])
            else:
                request_body = event['body']
        else:
            request_body = event
            
        question = validate_request_body(request_body)
        
        logger.info(f"Processing chat request: {question}")
        
        # 오케스트레이션 기반 검색 사용
        try:
            response = orchestrated_news_search(question)
            logger.info("Successfully used orchestrated search")
        except Exception as e:
            logger.warning(f"Orchestrated search failed: {e}, falling back to traditional approach")
            # 폴백: 기존 방식 사용
            if is_typo(question):
                logger.info("Typo detected – invoking Perplexity spellfix")
                try:
                    corrected_q, extra_ctx = perplexity_spellfix(question)
                except ChatbotError as ce:
                    logger.warning(f"Spellfix failed: {ce}")
                    corrected_q, extra_ctx = question, ""
                response = retrieve_and_generate_with_references(corrected_q, extra_context=extra_ctx)

            elif needs_external_search(question):
                logger.info("Date-related hard question – invoking Perplexity refine")
                try:
                    refined_q, extra_ctx = perplexity_refine(question)
                except ChatbotError as ce:
                    logger.warning(f"Refine failed: {ce}")
                    refined_q, extra_ctx = question, ""
                response = retrieve_and_generate_with_references(refined_q, extra_context=extra_ctx)

            else:  # easy path
                response = retrieve_and_generate_with_references(question)
        
        answer = response.get("output", {}).get("text", "답변을 생성할 수 없습니다")
        citations = response.get("citations", [])
        
        logger.info(f"Retrieved {len(citations)} citations")
        
        # 출처 정보 추출 (S3에서 원본 파일 읽어서 메타데이터 추출)
        sources = []
        processed_locations = set()  # 중복 처리 방지
        
        # 날짜 기반 필터링을 위한 target years 추출
        target_years = []
        current_year = datetime.now().year
        
        # 질문에서 년도 관련 키워드 분석
        if any(keyword in question.lower() for keyword in ["2025년", "올해", "최근", "현재", "지금"]):
            target_years = [str(current_year)]
        elif any(keyword in question.lower() for keyword in ["2024년", "작년", "지난해"]):
            target_years = [str(current_year-1)]
        elif "2023년" in question.lower():
            target_years = ["2023"]
        else:
            # 기본적으로 최근 2년 데이터 허용
            target_years = [str(current_year), str(current_year-1)]
        
        logger.info(f"Target years for filtering: {target_years} (based on question: '{question}')")
        
        logger.info(f"=== DEBUG: Full Bedrock response structure ===")
        logger.info(f"Citations count: {len(citations)}")
        
        for i, citation in enumerate(citations):
            logger.info(f"=== Processing citation {i} ===")
            logger.info(f"Citation structure: {json.dumps(citation, default=str, ensure_ascii=False)}")
            
            retrieved_refs = citation.get("retrievedReferences", [])
            logger.info(f"Retrieved references count: {len(retrieved_refs)}")
            
            for j, reference in enumerate(retrieved_refs):
                logger.info(f"=== Processing reference {j} ===")
                logger.info(f"Reference structure: {json.dumps(reference, default=str, ensure_ascii=False)}")
                
                content = reference.get("content", {}).get("text", "")
                location = reference.get("location", {})
                
                logger.info(f"Content length: {len(content)}")
                logger.info(f"Location structure: {json.dumps(location, default=str, ensure_ascii=False)}")
                
                # S3 location에서 URI 추출
                s3_location = location.get("s3Location", {})
                s3_uri = s3_location.get("uri", "")
                
                logger.info(f"Extracted S3 URI: '{s3_uri}'")
                
                if s3_uri and s3_uri not in processed_locations:
                    processed_locations.add(s3_uri)
                    
                    # S3에서 원본 파일을 읽어 최적의 기사 메타데이터 추출
                    try:
                        metadata = find_best_matching_article(s3_uri, content)
                        logger.info(f"Metadata extraction result: {metadata}")
                        
                        if metadata and metadata.get("title"):
                            # 날짜 기반 필터링 적용
                            article_date = metadata.get("date", "")
                            date_match = False
                            
                            # target_years에 해당하는 기사만 포함
                            if target_years:
                                date_match = any(year in article_date for year in target_years)
                                logger.info(f"Date filtering: '{article_date}' matches target years {target_years}: {date_match}")
                            else:
                                date_match = True  # target_years가 없으면 모든 기사 허용
                            
                            if date_match:
                                source_info = {
                                    "title": metadata["title"],
                                    "date": metadata["date"] or "날짜 없음", 
                                    "author": metadata["author"],
                                    "media": metadata["media"],
                                    "url": metadata["url"],
                                    "s3_uri": s3_uri
                                }
                                sources.append(source_info)
                                logger.info(f"✅ Successfully added source (date matched): {source_info}")
                            else:
                                logger.info(f"🚫 Filtered out source due to date mismatch: {metadata['title']} ({article_date})")
                        else:
                            logger.warning(f"❌ No valid metadata extracted from {s3_uri}")
                    except Exception as e:
                        logger.error(f"❌ Error extracting metadata from {s3_uri}: {str(e)}")
                else:
                    if not s3_uri:
                        logger.warning(f"❌ Empty S3 URI in reference {j}")
                        logger.info(f"Raw location data: {location}")
                    else:
                        logger.info(f"🔄 S3 URI already processed: {s3_uri}")
        
        logger.info(f"=== FINAL SOURCES COUNT: {len(sources)} ===")
        for idx, source in enumerate(sources):
            logger.info(f"Source {idx}: {source}")
        
        # 날짜 필터링 후 결과가 너무 적으면 경고 메시지
        if len(sources) < 2 and target_years:
            logger.warning(f"Very few sources ({len(sources)}) after date filtering for years {target_years}")
            # 날짜 범위를 확장하여 재검색 권유 메시지 추가
            if len(sources) == 0:
                logger.warning("No sources found matching date criteria, falling back to all available sources")
                # 날짜 필터링을 일시적으로 비활성화하여 재검색
                sources = []
                processed_locations = set()
                
                for i, citation in enumerate(citations):
                    retrieved_refs = citation.get("retrievedReferences", [])
                    for j, reference in enumerate(retrieved_refs):
                        content = reference.get("content", {}).get("text", "")
                        location = reference.get("location", {})
                        s3_location = location.get("s3Location", {})
                        s3_uri = s3_location.get("uri", "")
                        
                        if s3_uri and s3_uri not in processed_locations:
                            processed_locations.add(s3_uri)
                            try:
                                metadata = find_best_matching_article(s3_uri, content)
                                if metadata and metadata.get("title"):
                                    source_info = {
                                        "title": metadata["title"],
                                        "date": metadata["date"] or "날짜 없음", 
                                        "author": metadata["author"],
                                        "media": metadata["media"],
                                        "url": metadata["url"],
                                        "s3_uri": s3_uri
                                    }
                                    sources.append(source_info)
                                    logger.info(f"✅ Fallback: Added source without date filter: {source_info}")
                                    if len(sources) >= 3:  # 최소 3개 확보하면 중단
                                        break
                            except Exception as e:
                                logger.error(f"❌ Fallback error: {str(e)}")
                    if len(sources) >= 3:
                        break
        
        # 최대 5개 출처만 사용 (각주와 일치)
        top_sources = sources[:5]
        
        # AI가 이미 올바른 각주를 생성했으므로 그대로 사용
        footnoted_answer = answer
        
        # Perplexity 사용 여부 표시
        used_perplexity = bool(PERPLEXITY_API_KEY and (is_typo(question) or needs_external_search(question)))
        
        result = {
            "answer": footnoted_answer,
            "sources": top_sources,
            "question": question,
            "timestamp": response.get("sessionId", ""),
            "enhanced_search": used_perplexity
        }
        
        logger.info(f"Generated response with {len(top_sources)} sources")
        
        # API Gateway 응답 형식
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            },
            "body": json.dumps(result, ensure_ascii=False)
        }
        
    except ChatbotError as e:
        logger.warning(f"Chatbot error: {str(e)} – trying Perplexity fallback")
        try:
            fallback_answer = query_perplexity(question)
            result = {
                "answer": fallback_answer,
                "sources": [],  # Perplexity에서 별도 출처 제공하지 않음
                "question": question,
                "timestamp": datetime.utcnow().isoformat()
            }
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
                "body": json.dumps(result, ensure_ascii=False),
            }
        except ChatbotError as pe:
            # Perplexity도 실패 시 원래 400 응답
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "error": str(pe),
                    "type": "validation_error"
                }, ensure_ascii=False)
            }
        
    except Exception as e:
        logger.error(f"Unexpected error in handle_chat: {str(e)}")
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


def health_check(event: Dict[str, Any]) -> Dict[str, Any]:
    """헬스 체크 엔드포인트"""
    try:
        if not KNOWLEDGE_BASE_ID:
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "status": "unhealthy",
                    "message": "Knowledge Base ID가 설정되지 않았습니다"
                }, ensure_ascii=False)
            }
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "status": "healthy",
                "service": "news-chatbot-simple",
                "knowledge_base_id": KNOWLEDGE_BASE_ID,
                "version": "1.0.0"
            }, ensure_ascii=False)
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "status": "unhealthy",
                "error": str(e)
            }, ensure_ascii=False)
        }


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """Lambda 함수의 메인 핸들러"""
    logger.info(f"Processing request: {json.dumps(event, default=str)}")
    
    try:
        # HTTP 메서드와 경로에 따라 라우팅
        http_method = event.get("httpMethod", "POST")
        path = event.get("path", "/chat")
        
        if http_method == "OPTIONS":
            # CORS preflight 요청 처리
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization"
                },
                "body": ""
            }
        elif path == "/health" or path.endswith("/health"):
            return health_check(event)
        elif path == "/chat" or path.endswith("/chat"):
            return handle_chat(event)
        else:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "error": "Not Found",
                    "message": f"Path {path} not found"
                }, ensure_ascii=False)
            }
            
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


# 하위 호환성을 위한 별칭
handler = lambda_handler