#!/bin/bash

#
# News Chatbot Deployment Script
#
# 이 스크립트는 서울경제신문 뉴스 챗봇 API를 AWS에 배포하기 위한 자동화 스크립트입니다.
# CDK를 사용하여 필요한 인프라(Lambda, API Gateway, IAM 역할 등)를 생성합니다.
#
# 사용법: ./deploy-news-chatbot.sh
#
# 필수 조건:
# - AWS CLI 설치 및 설정 완료
# - Node.js 및 npm/pnpm 설치
# - CDK CLI 설치 (npm install -g aws-cdk)
#

set -e

echo "========================================="
echo "  News Chatbot API Deployment Script"
echo "========================================="

# 현재 디렉토리 확인
if [[ ! -f "cdk.json" ]]; then
    echo "Error: cdk.json 파일을 찾을 수 없습니다."
    echo "이 스크립트는 CDK 프로젝트 루트 디렉토리에서 실행해야 합니다."
    exit 1
fi

echo "1. 의존성 설치 중..."
npm install

echo "2. CDK 부트스트랩 확인 중..."
# CDK 부트스트랩이 필요한 경우에만 실행
if ! aws cloudformation describe-stacks --stack-name CDKToolkit &>/dev/null; then
    echo "CDK 부트스트랩을 실행합니다..."
    cdk bootstrap
else
    echo "CDK 부트스트랩이 이미 완료되어 있습니다."
fi

echo "3. CDK 스택 빌드 중..."
npm run build

echo "4. CDK diff 확인 중..."
cdk diff --context deploy:case=chatbot

echo "5. 배포를 시작합니다..."
echo "배포할 스택:"
echo "- CSCGenAILab-CommonStack (공통 리소스)"
echo "- CSCGenAILab-ChatbotStack (기존 챗봇)"
echo "- CSCGenAILab-NewsChatbotApiStack (뉴스 챗봇 API)"

read -p "계속 진행하시겠습니까? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "배포가 취소되었습니다."
    exit 0
fi

echo "6. CDK 배포 실행 중..."
cdk deploy --context deploy:case=chatbot --require-approval never

echo "========================================="
echo "  배포 완료!"
echo "========================================="

echo "배포된 리소스를 확인하려면:"
echo "1. AWS 콘솔에서 CloudFormation 스택을 확인하세요"
echo "2. API Gateway 콘솔에서 생성된 엔드포인트 URL을 확인하세요"
echo "3. Lambda 콘솔에서 함수가 정상적으로 생성되었는지 확인하세요"

echo ""
echo "API 테스트 예시:"
echo "curl -X POST [API_GATEWAY_URL]/prod/chat \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"question\": \"삼성전자 주가에 대해 알려주세요\"}'"

echo ""
echo "배포 스크립트가 완료되었습니다." 