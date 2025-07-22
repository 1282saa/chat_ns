# 뉴스 챗봇 데이터 관리 도구

이 디렉토리는 뉴스 챗봇의 Knowledge Base 데이터를 관리하기 위한 도구들을 포함합니다.

## 📁 디렉토리 구조

```
tools/
├── data_preprocessing/
│   ├── bigkinds_to_markdown.py  # BigKinds API → Markdown/JSONL 변환기
│   └── md_to_chunks.py          # 마크다운 → JSONL 변환기
└── README.md                    # 이 파일
```

## 🔧 도구 설명

### `data_preprocessing/bigkinds_to_markdown.py`

**용도**: BigKinds API를 통해 뉴스 데이터를 수집하고 마크다운 및 Knowledge Base 형식으로 변환

**주요 기능**:
- BigKinds API를 통한 뉴스 데이터 수집
- JSON → Markdown 변환
- Knowledge Base용 JSONL 생성
- 날짜별·카테고리별 파일 구조 생성

**사용법**:
```bash
cd tools/data_preprocessing

# 환경변수 설정
export BIGKINDS_KEY="your-api-key"

# 기본 사용법 (모든 형식으로 출력)
python bigkinds_to_markdown.py \
    --start-date 2023-02-17 \
    --end-date 2025-07-20 \
    --output-format all \
    --output-dir output

# 마크다운만 생성
python bigkinds_to_markdown.py \
    --output-format markdown \
    --output-dir markdown_output

# Knowledge Base용 JSONL만 생성
python bigkinds_to_markdown.py \
    --output-format jsonl \
    --output-dir kb_output
```

### `data_preprocessing/md_to_chunks.py`

**용도**: 기존 마크다운 형식의 뉴스 파일을 Bedrock Knowledge Base용 JSONL 형식으로 변환

**주요 기능**:
- 마크다운 뉴스 파일 파싱
- 기사별 메타데이터 추출 (제목, 날짜, URL, 카테고리)
- 텍스트를 700바이트 단위로 청킹
- OpenSearch Bulk API 호환 JSONL 출력

**사용법**:
```bash
cd tools/data_preprocessing

# 예시: 2016년 4월 10일 뉴스 데이터 변환
python md_to_chunks.py \
    --input_dir ../../서울경제뉴스데이터_마크다운/2016/04/10 \
    --output out/2016_04_10_chunks.jsonl \
    --chunk_bytes 700
```

**출력 형식** (JSONL):
```json
{
  "chunk": "기사 내용 텍스트 청크...",
  "path": "2016/04/10/filename.md",
  "article_idx": 1,
  "chunk_idx": 1,
  "title": "기사 제목",
  "date": "2016-04-10",
  "url": "https://example.com/news/123",
  "category": "경제"
}
```

## 🔄 워크플로우

### 새로운 뉴스 데이터 추가

1. **데이터 전처리**:
   ```bash
   python tools/data_preprocessing/md_to_chunks.py \
       --input_dir [마크다운_데이터_경로] \
       --output chunks/new_data.jsonl
   ```

2. **S3 업로드**:
   ```bash
   aws s3 cp chunks/new_data.jsonl s3://seoul-economic-news-data-2025/
   ```

3. **Knowledge Base 동기화**:
   - AWS Console에서 Knowledge Base 데이터 소스 동기화 실행
   - 또는 AWS CLI로 동기화 작업 시작

4. **테스트**:
   - 챗봇에서 새로운 데이터 관련 질문으로 테스트

### Knowledge Base 재구축

전체 데이터를 다시 처리해야 하는 경우:

1. 모든 마크다운 데이터를 JSONL로 변환
2. S3 버킷 내용 교체
3. Knowledge Base 전체 재동기화

## ⚠️ 주의사항

- **백업**: 기존 데이터를 교체하기 전에 반드시 백업
- **테스트**: 프로덕션 환경에 적용하기 전에 개발 환경에서 테스트
- **용량**: 대용량 데이터 처리 시 충분한 디스크 공간 확보
- **인코딩**: 한글 데이터는 UTF-8 인코딩 확인

## 🔗 관련 리소스

- **S3 버킷**: `seoul-economic-news-data-2025`
- **Knowledge Base ID**: `PGQV3JXPET`
- **현재 챗봇 API**: https://gzb9wui0z9.execute-api.ap-northeast-2.amazonaws.com/prod