#!/bin/bash

#
# Simple News Chatbot Deployment Script
#
# 뉴스 챗봇 API를 간단하게 배포하기 위한 스크립트입니다.
# 기존 프로젝트의 복잡한 의존성 없이 필요한 부분만 배포합니다.
#

set -e

echo "========================================="
echo "  Simple News Chatbot Deployment"
echo "========================================="

# 지식 기반 ID 설정
KNOWLEDGE_BASE_ID="PGQV3JXPET"

echo "Knowledge Base ID: $KNOWLEDGE_BASE_ID"
echo ""

# CDK 부트스트랩 확인
echo "1. CDK 부트스트랩 확인 중..."
if ! aws cloudformation describe-stacks --stack-name CDKToolkit &>/dev/null; then
    echo "CDK 부트스트랩을 실행합니다..."
    cdk bootstrap
else
    echo "CDK 부트스트랩이 이미 완료되어 있습니다."
fi

echo ""
echo "2. 뉴스 챗봇 스택을 배포합니다..."
echo "배포할 리소스:"
echo "- Lambda Function (news-chatbot-handler)"
echo "- API Gateway (News Chatbot API)"  
echo "- IAM Role (Bedrock 접근 권한)"
echo "- CloudWatch Logs"
echo ""

read -p "계속 진행하시겠습니까? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "배포가 취소되었습니다."
    exit 0
fi

echo "3. CDK 배포 실행 중..."

# CDK 배포 (독립 스택 사용)
npx cdk deploy NewsChatbotStack \
    --app "npx ts-node src/news-chatbot-main.ts" \
    --context knowledgeBaseId=$KNOWLEDGE_BASE_ID \
    --require-approval never

echo ""
echo "========================================="
echo "  배포 완료!"
echo "========================================="

# 배포된 리소스 정보 출력
echo "배포된 리소스:"
echo "1. Lambda Function: news-chatbot-handler"
echo "2. API Gateway: News Chatbot API"
echo ""

echo "CloudFormation 출력값을 확인하여 API URL을 얻으세요:"
echo "aws cloudformation describe-stacks --stack-name NewsChatbotStack --query 'Stacks[0].Outputs'"
echo ""

echo "API 테스트 예시:"
echo "curl -X POST [API_URL]/prod/chat \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"question\": \"삼성전자 주가는 어떤가요?\"}'"
echo ""
echo "헬스 체크:"
echo "curl [API_URL]/prod/health"

echo ""
echo "배포가 완료되었습니다!" 