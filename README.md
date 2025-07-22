# 서울경제 뉴스 챗봇

AWS Bedrock Knowledge Base와 Perplexity AI를 활용한 지능형 뉴스 검색 챗봇입니다.

## 🚀 주요 기능

- **오케스트레이션 기반 검색**: 다단계 검색 전략으로 정확도 향상
- **날짜 기반 필터링**: 질문 맥락에 맞는 시기의 기사만 선별
- **스마트 로딩**: 날짜 관련 질문시 AI 강화 모드 표시
- **실시간 검색**: Perplexity AI를 통한 최신 정보 보강

## 🏗️ 아키텍처

```
User Query → API Gateway → Lambda Function → Bedrock Knowledge Base
                                    ↓
                            Orchestration Engine
                                    ↓
                          Date Filtering & Analysis
                                    ↓
                            Formatted Response
```

## 📦 배포

### 자동 배포 (GitHub Actions)

1. GitHub Secrets에 다음 값들을 설정:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY` 
   - `PERPLEXITY_API_KEY`

2. main/develop 브랜치에 푸시하면 자동 배포됩니다.

### 수동 배포

```bash
npm install
export PERPLEXITY_API_KEY="your-api-key"
cdk deploy NewsChatbotStack --app "npx ts-node src/news-chatbot-main.ts"
```

## 🧪 테스트

웹 인터페이스: `test-chatbot-final.html`을 브라우저에서 열기

API 직접 테스트:
```bash
curl -X POST "https://your-api-url/prod/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "2025년 주요 경제 이슈는?"}'
```

## 🔧 환경 변수

- `KNOWLEDGE_BASE_ID`: AWS Bedrock Knowledge Base ID
- `PERPLEXITY_API_KEY`: Perplexity AI API 키
- `LOG_LEVEL`: 로그 레벨 (기본값: INFO)

## 📝 지원되는 질문 유형

- 날짜 기반 질문: "2025년 이슈", "올해 동향", "최근 뉴스"
- 키워드 검색: "삼성전자", "부동산", "금리"
- 복합 질문: "최근 반도체 업계 동향은?"

## 🔄 CI/CD

GitHub Actions를 통한 자동 배포:
- Pull Request시 검증
- main/develop 브랜치 푸시시 자동 배포
- AWS CDK 기반 인프라 관리

## 📊 로그 모니터링

AWS CloudWatch에서 Lambda 함수 로그 확인:
```bash
aws logs tail /aws/lambda/news-chatbot-handler --since 1h
```