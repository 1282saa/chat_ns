# GitHub CI/CD 설정 가이드

## 1. GitHub 레포지토리 준비

### 레포지토리에 코드 푸시
```bash
cd /path/to/cdk_infra
git init
git add .
git commit -m "Initial commit: News Chatbot with orchestration-based search"
git branch -M main
git remote add origin https://github.com/1282saa/chat_ns.git
git push -u origin main
```

## 2. GitHub Secrets 설정

GitHub 레포지토리 → Settings → Secrets and variables → Actions에서 다음 시크릿들을 추가:

### 필수 시크릿:
- **`AWS_ACCESS_KEY_ID`**: AWS Access Key ID
- **`AWS_SECRET_ACCESS_KEY`**: AWS Secret Access Key  
- **`PERPLEXITY_API_KEY`**: `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`

### AWS 자격증명 생성 방법:

1. **AWS IAM 콘솔** 접속
2. **사용자(Users)** → **사용자 추가**
3. 사용자 이름: `github-actions-deployer`
4. **Access key - Programmatic access** 선택
5. 권한 정책 연결:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "cloudformation:*",
           "lambda:*",
           "apigateway:*",
           "iam:*",
           "logs:*",
           "s3:*",
           "bedrock:*"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

## 3. 자동 배포 프로세스

### 배포 트리거:
- **main 브랜치에 푸시**: 프로덕션 배포
- **develop 브랜치에 푸시**: 개발환경 배포  
- **Pull Request**: 검증만 실행

### 배포 단계:
1. ✅ 코드 체크아웃
2. ✅ Node.js 18 설치
3. ✅ 의존성 설치 (`npm ci`)
4. ✅ 테스트 실행 (있는 경우)
5. ✅ AWS 자격증명 설정
6. ✅ CDK 설치
7. ✅ CDK Bootstrap (필요시)
8. ✅ 배포 실행

## 4. 배포 모니터링

### GitHub Actions 확인:
- 레포지토리 → **Actions** 탭
- 실행 중/완료된 워크플로우 확인
- 로그 및 에러 메시지 확인

### AWS 콘솔 확인:
- **CloudFormation** → `NewsChatbotStack` 스택 상태
- **Lambda** → `news-chatbot-handler` 함수
- **API Gateway** → 엔드포인트 URL

## 5. 환경별 설정 (선택사항)

### 다중 환경 지원을 위한 워크플로우 수정:
```yaml
- name: Deploy to Development
  if: github.ref == 'refs/heads/develop'
  run: |
    export PERPLEXITY_API_KEY="${{ secrets.PERPLEXITY_API_KEY }}"
    cdk deploy NewsChatbotStack-dev --app "npx ts-node src/news-chatbot-main.ts" --require-approval never

- name: Deploy to Production  
  if: github.ref == 'refs/heads/main'
  run: |
    export PERPLEXITY_API_KEY="${{ secrets.PERPLEXITY_API_KEY }}"
    cdk deploy NewsChatbotStack --app "npx ts-node src/news-chatbot-main.ts" --require-approval never
```

## 6. 트러블슈팅

### 일반적인 오류와 해결방법:

**1. AWS 권한 오류**
```
AccessDenied: User is not authorized to perform: cloudformation:CreateStack
```
→ IAM 사용자에게 적절한 권한 추가

**2. CDK Bootstrap 오류**
```
This stack uses assets, so the toolkit stack must be deployed
```
→ 해당 리전에 CDK Bootstrap 실행:
```bash
cdk bootstrap aws://ACCOUNT-NUMBER/ap-northeast-2
```

**3. Perplexity API 키 오류**
```
Perplexity API 호출 실패
```
→ GitHub Secrets에서 `PERPLEXITY_API_KEY` 확인

## 7. 배포 후 검증

배포 완료 후 다음을 확인:
1. API Gateway URL이 출력되었는지 확인
2. 웹 인터페이스에서 정상 작동 테스트
3. CloudWatch 로그에서 에러 없는지 확인

```bash
# API 테스트
curl -X POST "https://your-api-url/prod/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "2025년 주요 이슈는?"}'
```