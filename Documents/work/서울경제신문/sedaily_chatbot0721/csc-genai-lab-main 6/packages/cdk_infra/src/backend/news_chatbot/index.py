import json
import logging
import os
import boto3
from datetime import datetime
import re
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')
bedrock_runtime = boto3.client('bedrock-runtime')

KNOWLEDGE_BASE_ID = os.environ.get('KNOWLEDGE_BASE_ID', 'PGQV3JXPET')
MODEL_ID = os.environ.get('MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
PERPLEXITY_API_KEY = os.environ.get('PERPLEXITY_API_KEY')

def lambda_handler(event, context):
    try:
        logger.info(f"Event: {json.dumps(event)}")
        
        if event.get('httpMethod') == 'GET' and event.get('path') == '/health':
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
                'body': json.dumps({'status': 'healthy', 'timestamp': datetime.now().isoformat()})
            }
        
        body = json.loads(event['body'])
        user_query = body.get('message', '')
        
        if not user_query:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
                'body': json.dumps({'error': 'Message is required'})
            }
        
        # Check if query contains recent date keywords
        should_use_perplexity = contains_recent_date_keywords(user_query)
        
        if should_use_perplexity and PERPLEXITY_API_KEY:
            logger.info("Using Perplexity AI for real-time search")
            response = search_with_perplexity(user_query)
        else:
            logger.info("Using Knowledge Base for historical data")
            response = search_knowledge_base(user_query)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
            },
            'body': json.dumps(response)
        }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
            },
            'body': json.dumps({'error': 'Internal server error'})
        }

def contains_recent_date_keywords(query):
    recent_keywords = [
        '오늘', '어제', '이번주', '이번달', '최근', '지금', '현재',
        '최신', '방금', '금일', '실시간', '지금', '현재'
    ]
    
    current_year = datetime.now().year
    year_keywords = [str(current_year), str(current_year - 1)]
    
    query_lower = query.lower()
    
    for keyword in recent_keywords + year_keywords:
        if keyword in query_lower:
            return True
    
    return False

def search_with_perplexity(query):
    try:
        url = "https://api.perplexity.ai/chat/completions"
        
        payload = {
            "model": "llama-3.1-sonar-large-128k-online",
            "messages": [
                {
                    "role": "system",
                    "content": "당신은 서울경제신문의 뉴스 어시스턴트입니다. 한국 경제 뉴스를 중심으로 정확하고 신뢰할 수 있는 정보를 제공해주세요. 답변은 한국어로 해주시고, 출처를 명시해주세요."
                },
                {
                    "role": "user", 
                    "content": f"한국 경제와 관련된 다음 질문에 답해주세요: {query}"
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.2,
            "top_p": 0.9,
            "return_citations": True,
            "search_domain_filter": ["kr"],
            "search_recency_filter": "week"
        }
        
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        content = data['choices'][0]['message']['content']
        
        citations = []
        if 'citations' in data:
            citations = data['citations']
        
        return {
            'answer': content,
            'sources': citations,
            'search_type': 'perplexity',
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Perplexity API error: {str(e)}")
        return search_knowledge_base(query)

def search_knowledge_base(query):
    try:
        response = bedrock_agent_runtime.retrieve_and_generate(
            input={'text': query},
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': KNOWLEDGE_BASE_ID,
                    'modelArn': f'arn:aws:bedrock:ap-northeast-2::foundation-model/{MODEL_ID}',
                    'retrievalConfiguration': {
                        'vectorSearchConfiguration': {
                            'numberOfResults': 10
                        }
                    },
                    'generationConfiguration': {
                        'promptTemplate': {
                            'textPromptTemplate': '''당신은 서울경제신문의 뉴스 어시스턴트입니다. 
주어진 컨텍스트를 바탕으로 사용자의 질문에 정확하고 유용한 답변을 제공해주세요.

컨텍스트: $search_results$

사용자 질문: $query$

답변 시 다음 사항을 지켜주세요:
1. 한국어로 답변해주세요
2. 정확한 정보만 제공하고, 확실하지 않은 내용은 언급하지 마세요
3. 가능한 한 구체적인 날짜, 수치, 출처를 포함해주세요
4. 답변 끝에 관련 출처를 [1], [2] 형식으로 번호를 매겨 표시해주세요

답변:'''
                        }
                    }
                }
            }
        )
        
        answer = response.get('output', {}).get('text', '')
        sources = []
        
        if 'citations' in response:
            for i, citation in enumerate(response['citations'], 1):
                for reference in citation.get('retrievedReferences', []):
                    source_info = {
                        'number': i,
                        'title': reference.get('metadata', {}).get('title', ''),
                        'url': reference.get('metadata', {}).get('url', ''),
                        'date': reference.get('metadata', {}).get('date', ''),
                        'category': reference.get('metadata', {}).get('category', ''),
                        'content': reference.get('content', {}).get('text', '')[:200] + '...'
                    }
                    sources.append(source_info)
        
        return {
            'answer': answer,
            'sources': sources,
            'search_type': 'knowledge_base',
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Knowledge Base error: {str(e)}")
        raise