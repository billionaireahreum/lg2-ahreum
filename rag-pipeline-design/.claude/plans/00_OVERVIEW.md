# Plan 00 - RAG 파이프라인 전체 설계

**목표**: VOD 메타데이터 품질 보완 + 텍스트 임베딩 생성 → vod_embedding 저장
**브랜치**: `rag-pipeline-design`
**선행 조건**: Phase 1 완료 (users, vod, watch_history, vod_embedding 테이블 존재)

---

## 1. 전체 흐름

```
[Phase 1 DB]
vod 테이블 (166,159개)
    │
    ├── director NULL 313건
    └── smry     NULL  28건
          │
          ▼
[Step 1] 01_fill_missing.py
  Claude API (claude-haiku-4-5)로 결측치 추론/생성
  → vod 테이블 UPDATE (director, smry, rag_processed, rag_source)
          │
          ▼
[Step 2] 02_generate_embeddings.py
  sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2, 384d)
  입력: asset_nm + genre + genre_detail + ct_cl + director + cast_lead + smry
  배치 256건씩 인코딩
          │
          ▼
[Step 3] pgvector에 벡터 저장
  schema/pgvector_setup.sql 실행 (최초 1회)
  vod_embedding 테이블: 메타데이터 + content_vector(384) 컬럼
  HNSW 인덱스 (cosine similarity)
```

---

## 2. 파일 구조

```
rag-pipeline-design/
├── .claude/
│   └── plans/
│       ├── 00_OVERVIEW.md            # 이 파일
│       ├── 01_MISSING_VALUES.md      # 결측치 보완 설계
│       ├── 02_EMBEDDING.md           # 임베딩 전략
│       └── 03_PGVECTOR_SETUP.md      # pgvector 설정
├── pipeline/
│   ├── config.py                     # DB/API 설정
│   ├── db.py                         # DB 연결 헬퍼
│   ├── 01_fill_missing.py            # 결측치 보완 (Claude API)
│   └── 02_generate_embeddings.py     # 임베딩 생성 + pgvector 저장
├── schema/
│   └── pgvector_setup.sql            # pgvector 확장 + 벡터 컬럼 추가
└── requirements.txt
```

---

## 3. 실행 순서

```bash
# 0. pgvector 설정 (최초 1회, DB 관리자 권한 필요)
psql -d vod_recommendation -f schema/pgvector_setup.sql

# 1. 환경변수 설정
export ANTHROPIC_API_KEY="..."
export DB_HOST="localhost"
export DB_PASSWORD="..."

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 결측치 보완 (Claude API 호출 - API 비용 발생)
python pipeline/01_fill_missing.py

# 4. 임베딩 생성 + pgvector 저장 (로컬 CPU/GPU 연산)
python pipeline/02_generate_embeddings.py
```

---

## 4. 기술 스택

| 컴포넌트 | 선택 | 이유 |
|---------|------|------|
| 결측치 보완 LLM | Claude Haiku (claude-haiku-4-5-20251001) | 빠름, 비용 저렴, 한국어 강함 |
| 임베딩 모델 | paraphrase-multilingual-MiniLM-L12-v2 (384d) | 무료, 로컬, 한국어 지원 |
| 벡터 DB | pgvector (PostgreSQL 확장) | VOD 166k개 → pgvector로 충분 |
| 인덱스 | HNSW (m=16, ef_construction=64) | ANN 검색 < 50ms |

---

## 5. 예상 처리량

| 단계 | 건수 | 예상 소요 시간 |
|------|------|-------------|
| director 결측치 보완 | 313건 | ~5분 (API 레이트 리밋) |
| smry 결측치 보완 | 28건 | ~1분 |
| 임베딩 생성 (CPU) | 166,159건 | ~30분 (배치 256) |
| pgvector 저장 | 166,159건 | ~10분 |

---

## 6. 설계 결정사항

### 6.1 임베딩 모델 선택
- VOD 166k개는 pgvector HNSW로 충분 (Milvus 불필요)
- 한국어 콘텐츠 → 다국어 모델 필수 → `paraphrase-multilingual-MiniLM-L12-v2`
- 향후 스케일 시: `BAAI/bge-m3` (1024d) 또는 OpenAI `text-embedding-3-large` (1536d) 교체

### 6.2 결측치 보완 전략
- director: 제목 + 장르 + 제공사 → Claude 추론 (정보 없으면 NULL 유지)
- smry: 제목 + 장르 + 감독 + 주연 → Claude 생성 (2-3문장 한국어)
- 보완 출처 기록: rag_source = 'CLAUDE_INFERENCE' | 'CLAUDE_GENERATED'

### 6.3 멱등성(Idempotency)
- `01_fill_missing.py`: `rag_processed = FALSE` 조건으로 재실행 안전
- `02_generate_embeddings.py`: `ON CONFLICT DO UPDATE`로 재실행 안전
