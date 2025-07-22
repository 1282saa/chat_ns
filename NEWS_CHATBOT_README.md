# News Chatbot API

서울경제신문 뉴스 데이터를 기반으로 한 챗봇 API 서비스입니다. AWS Bedrock Knowledge Base를 활용하여 사용자의 질문에 대해 관련 뉴스를 검색하고 요약된 답변을 제공합니다.

## 아키텍처 개요

```
사용자 질문 → API Gateway → Lambda Function → Bedrock Knowledge Base → 뉴스 데이터 검색 → 답변 생성
```

### 주요 구성요소

- **API Gateway**: REST API 엔드포인트 제공
- **Lambda Function**: 챗봇 로직 처리 (Python 3.11)
- **Bedrock Knowledge Base**: 뉴스 데이터 검색 및 답변 생성
- **IAM Role**: 최소 권한 원칙에 따른 보안 설정

## 파일 구조

```
src/
├── stacks/
│   └── news-chatbot-api-stack.ts     # CDK 스택 정의
├── backend/
│   └── news_chatbot/
│       ├── handler.py                # Lambda 함수 메인 코드
│       └── requirements.txt          # Python 의존성
├── deploy-news-chatbot.sh            # 배포 자동화 스크립트
└── NEWS_CHATBOT_README.md           # 이 파일
```

## 사전 요구사항

### 1. 개발 환경

- Node.js (v18 이상)
- Python 3.11
- AWS CLI 설치 및 설정
- CDK CLI 설치: `npm install -g aws-cdk`

### 2. AWS 리소스

- AWS 계정 및 적절한 권한
- Bedrock Knowledge Base가 생성되어 있어야 함
- S3에 뉴스 데이터가 업로드되어 있어야 함

### 3. 환경 변수

배포 시 자동으로 설정되는 환경 변수:

- `KNOWLEDGE_BASE_ID`: Bedrock Knowledge Base ID
- `LOG_LEVEL`: 로그 레벨 (기본값: INFO)

## 배포 방법

### 자동 배포 (권장)

```bash
cd packages/cdk_infra
./deploy-news-chatbot.sh
```

### 수동 배포

```bash
cd packages/cdk_infra

# 의존성 설치
npm install

# CDK 부트스트랩 (최초 1회만)
cdk bootstrap

# 빌드
npm run build

# 배포
cdk deploy --context deploy:case=chatbot
```

## API 사용법

### 엔드포인트

#### POST /prod/chat

챗봇과 대화하기 위한 메인 엔드포인트

**요청 형식:**

```json
{
  "question": "삼성전자 주가에 대해 알려주세요"
}
```

**응답 형식:**

```json
{
  "answer": "생성된 답변 텍스트",
  "sources": [
    {
      "content": "관련 뉴스 내용 일부",
      "location": {
        "s3Location": {
          "uri": "s3://bucket/path/to/file.md"
        }
      }
    }
  ],
  "question": "사용자의 원본 질문",
  "timestamp": "응답 생성 시간"
}
```

**오류 응답:**

```json
{
    "error": "오류 메시지",
    "type": "validation_error" | "internal_error"
}
```

#### GET /prod/health

서비스 상태 확인

**응답:**

```json
{
  "status": "healthy",
  "service": "news-chatbot",
  "knowledge_base_id": "PGQV3JXPET",
  "version": "1.0.0"
}
```

### 사용 예시

#### cURL

```bash
curl -X POST https://[API_GATEWAY_URL]/prod/chat \
  -H 'Content-Type: application/json' \
  -d '{"question": "최근 삼성전자 실적은 어떤가요?"}'
```

#### Python

```python
import requests
import json

url = "https://[API_GATEWAY_URL]/prod/chat"
payload = {"question": "최근 경제 동향을 알려주세요"}
headers = {"Content-Type": "application/json"}

response = requests.post(url, data=json.dumps(payload), headers=headers)
result = response.json()

print(f"답변: {result['answer']}")
```

#### JavaScript

```javascript
const apiUrl = "https://[API_GATEWAY_URL]/prod/chat";
const question = "코스피 지수 전망은 어떤가요?";

fetch(apiUrl, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ question: question }),
})
  .then((response) => response.json())
  .then((data) => {
    console.log("답변:", data.answer);
    console.log("출처:", data.sources);
  });
```

## 모니터링 및 로깅

### CloudWatch 로그

- Lambda 함수 로그: `/aws/lambda/news-chatbot-handler`
- API Gateway 액세스 로그: 자동 생성된 로그 그룹

### 주요 메트릭

- API Gateway: 요청 수, 응답 시간, 오류율
- Lambda: 실행 시간, 메모리 사용량, 오류 수
- Bedrock: API 호출 수, 토큰 사용량

## 문제 해결

### 일반적인 오류

#### "Knowledge Base ID가 설정되지 않았습니다"

- 환경 변수 `KNOWLEDGE_BASE_ID`가 올바르게 설정되었는지 확인
- CDK 스택에서 올바른 Knowledge Base ID가 전달되었는지 확인

#### "지식 기반 검색 중 오류가 발생했습니다"

- Bedrock Knowledge Base가 활성화되어 있는지 확인
- 데이터 동기화(Sync)가 완료되었는지 확인
- IAM 권한이 올바르게 설정되었는지 확인

#### "요청 본문은 JSON 객체여야 합니다"

- Content-Type 헤더가 `application/json`으로 설정되었는지 확인
- 요청 본문이 유효한 JSON 형식인지 확인

### 로그 확인

```bash
# Lambda 함수 로그 확인
aws logs tail /aws/lambda/news-chatbot-handler --follow

# 최근 오류 로그만 확인
aws logs filter-log-events \
  --log-group-name /aws/lambda/news-chatbot-handler \
  --filter-pattern "ERROR"
```

## 보안 고려사항

### IAM 권한

- Lambda 함수는 최소한의 권한만 가짐
- Bedrock Knowledge Base 접근 권한만 부여
- CloudWatch Logs 쓰기 권한

### API 보안

- CORS 설정으로 크로스 오리진 요청 제어
- 현재 버전에서는 인증 없음 (향후 버전에서 추가 예정)

## 향후 개선 계획

### Phase 2: 고급 기능

- 외부 API 연동 (Perplexity 등)
- 멀티 에이전트 워크플로우
- 인증 및 권한 관리

### Phase 3: 최적화

- 응답 캐싱
- 청킹 전략 개선
- 성능 튜닝

## 지원 및 문의

문제가 발생하거나 개선 사항이 있으시면 다음을 확인해 주세요:

1. CloudWatch 로그에서 상세한 오류 정보 확인
2. API Gateway 콘솔에서 요청/응답 추적
3. Bedrock 콘솔에서 Knowledge Base 상태 확인

## 라이선스

이 프로젝트는 Amazon Software License에 따라 라이선스가 부여됩니다.
