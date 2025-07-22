# 서울경제 뉴스 챗봇 프로젝트 구조

## 개요
이 프로젝트는 AWS CDK를 사용하여 서울경제신문의 뉴스 챗봇을 배포하는 인프라입니다.

## 최종 정리된 프로젝트 구조

```
packages/cdk_infra/
├── src/
│   ├── backend/
│   │   └── news_chatbot/
│   │       ├── index.py           # 메인 Lambda 함수 코드
│   │       └── requirements.txt   # Python 의존성
│   ├── frontend/
│   │   └── index.html            # 웹 인터페이스 (Tailwind CSS)
│   ├── assets/
│   │   └── knowledgebase/        # Knowledge Base 테스트 문서들
│   ├── stacks/
│   │   └── news-chatbot-standalone-stack.ts  # CDK 스택 정의
│   └── news-chatbot-main.ts      # CDK 앱 진입점
├── tools/
│   ├── data_preprocessing/
│   │   └── md_to_chunks.py       # 뉴스 데이터 전처리 도구
│   └── README.md                 # 도구 사용법 가이드
├── deploy-news-chatbot.sh        # 배포 스크립트
├── package.json                  # Node.js 의존성
├── cdk.json                      # CDK 설정
├── jest.config.js               # 테스트 설정
└── PROJECT_STRUCTURE.md         # 이 문서
```

## 배포된 리소스

### 백엔드
- **Lambda Function**: `news-chatbot-handler`
  - Runtime: Python 3.11
  - Memory: 1024MB
  - Timeout: 5분
  - Bedrock Knowledge Base 연동
  - Perplexity AI 통합

### 프론트엔드
- **S3 Bucket**: 정적 웹사이트 호스팅
- **CloudFront**: CDN 배포
- **웹 인터페이스**: Tailwind CSS 기반 반응형 디자인

### API
- **API Gateway**: RESTful API 엔드포인트
- **CORS**: 모든 오리진 허용
- **엔드포인트**:
  - `POST /chat`: 챗봇 질의응답
  - `GET /health`: 헬스체크

## 배포 URL
- **Frontend**: CloudFront 배포 URL
- **API**: API Gateway 엔드포인트 URL

## 개발 환경 설정

### 필수 환경변수
- `PERPLEXITY_API_KEY`: Perplexity AI API 키
- `CDK_DEFAULT_ACCOUNT`: AWS 계정 ID
- `CDK_DEFAULT_REGION`: AWS 리전 (기본: ap-northeast-2)

### GitHub Actions CI/CD
- **워크플로우**: `.github/workflows/deploy.yml`
- **트리거**: main, develop 브랜치 푸시
- **단계**: 테스트 → 빌드 → 배포

## 주요 기능

### 챗봇 기능
1. **RAG (Retrieval-Augmented Generation)**
   - Bedrock Knowledge Base 검색
   - 관련 문서 찾기 및 답변 생성

2. **하이브리드 검색**
   - 날짜 키워드 감지
   - Perplexity AI 실시간 검색
   - 최신 뉴스 정보 제공

3. **사용자 인터페이스**
   - 실시간 채팅 인터페이스
   - 출처 링크 제공
   - 각주 클릭으로 원문 이동

### 보안 및 성능
- IAM 역할 기반 권한 관리
- CloudWatch 로깅
- CDK NAG 보안 검사
- CloudFront 캐싱 최적화

## 데이터 관리 도구

### `tools/data_preprocessing/md_to_chunks.py`
뉴스 데이터를 Knowledge Base용 형식으로 변환하는 도구입니다.

**사용법**:
```bash
cd tools/data_preprocessing
python md_to_chunks.py \
    --input_dir [마크다운_파일_경로] \
    --output [출력_JSONL_파일] \
    --chunk_bytes 700
```

자세한 사용법은 `tools/README.md`를 참고하세요.

## 대대적인 정리 작업 (2025-07-22)

### 삭제된 불필요한 요소들
- **루트 레벨**: docs/, tools/, 각종 설정 파일들
- **ReactJS UI 패키지**: packages/reactjs_ui/ 전체
- **불필요한 백엔드**: agents/, basic_rest_api/, chat_summary/, email_processing/, rest_apis/
- **불필요한 스택**: text2sql/, chatbot/, 기타 스택 파일들
- **기타**: constructs/, prompt/, utils/, 백업 파일들, 테스트 파일들

### 보존된 핵심 요소들
- **뉴스 챗봇 Lambda 코드**: src/backend/news_chatbot/
- **프론트엔드**: src/frontend/index.html
- **CDK 스택**: news-chatbot-standalone-stack.ts
- **배포 설정**: GitHub Actions, CDK 설정 파일들

### 추가된 요소들
- **데이터 관리 도구**: tools/data_preprocessing/ (기존 외부 도구를 프로젝트 내로 이동)

## 다음 개발 단계
✅ **완전히 정리된 깔끔한 프로젝트 구조**  
✅ **데이터 관리 도구 통합**  
이제 뉴스 챗봇 개발에만 집중할 수 있는 최적화된 환경이 준비되었습니다.