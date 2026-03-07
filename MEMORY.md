# VOD 추천 시스템 - 개발 메모리

## 프로젝트 기본 정보
- **GitHub**: `https://github.com/billionaireahreum/lg2-ahreum.git`
- **작업 경로**: `C:\Users\army5\Desktop\Lghellovision2`
- **프로젝트명**: LG 헬로비전 VOD 추천 + 영상인식 마켓플레이스 (1조 2차 프로젝트)
- **팀원**: 박아름, 황대원, 최기문, 이가원, 신정윤

## 현재 진행 상태 (2026-03-07 기준)

### 완료된 작업
| 브랜치 | 내용 | 상태 |
|--------|------|------|
| `database-design` | PostgreSQL DB 설계 + CSV 마이그레이션 | 완료, master 머지 |
| `rag-pipeline-design` | RAG 파이프라인 설계 + 임베딩 스크립트 | 완료, master 머지 |

### DB 마이그레이션 완료 (PostgreSQL)
- users: 242,702명 (35MB)
- vod: 166,159개 (81MB)
- watch_history: 3,992,530건 (637MB)
- vod_embedding, user_embedding, vod_recommendation: 테이블 생성 완료 (데이터 없음)

### DB 백업 파일
- `C:\Users\army5\Desktop\vod_backup.dump` — 다른 PC 이전용

## 다음 작업 (새 노트북에서 이어서)

### 즉시 해야 할 것
1. **다른 PC에 PostgreSQL 설치 + dump 복원**
   ```bash
   # 복원 명령어
   pg_restore -U postgres -d vod_recommendation -Fc vod_backup.dump
   ```

2. **pgvector 설치** (PostgreSQL 확장)
   - GitHub에서 `pgvector windows postgresql` 버전에 맞게 다운로드
   - lib, share 파일 복사 후 `CREATE EXTENSION vector;`

3. **pgvector 설정 SQL 실행**
   ```
   psql -U postgres -d vod_recommendation -f rag-pipeline-design/schema/pgvector_setup.sql
   ```

4. **결측치 보완 파이프라인 실행** (TMDB API)
   - 실제 director NULL: 19,037건 (TMDB 성공률 낮음 - 한국 케이블 콘텐츠)
   - Groq API(무료) 또는 로컬 Ollama로 RAG 구현 고려
   - 32GB RAM → Ollama llama3:8b 실행 가능

5. **임베딩 생성**
   ```
   python rag-pipeline-design/pipeline/02_generate_embeddings.py
   ```
   - 모델: paraphrase-multilingual-MiniLM-L12-v2 (384d)
   - 166,159개 VOD → 약 30분 소요

## 프로젝트 전체 아키텍처 (기획서 기준)

### 두 가지 핵심 기능
1. **하이브리드 VOD 추천**: MF + Vector Search + LLM 감성 문구
2. **영상인식 마켓플레이스**: YOLOv8 → 농산물 인식 → Naver API 상품 매칭

### 기술 스택
- DB: PostgreSQL + pgvector
- 추천: Matrix Factorization (Surprise) + Vector Search
- LLM: LG Exaone 4.0 (감성 문구)
- Backend: FastAPI
- Frontend: Streamlit

### 전체 개발 단계
```
[완료] Phase 1: DB 설계 + 마이그레이션
[진행중] Phase 2: RAG 파이프라인 (결측치 보완 + 임베딩)
[예정] Phase 3: Matrix Factorization 추천 엔진
[예정] Phase 4: LLM 감성 문구 + FastAPI
[예정] Phase 5: Streamlit UI
[예정] Phase 6: 영상인식 마켓플레이스 (YOLOv8)
```

## 실제 데이터 규모
- 시청 이력: 3,992,530건
- 고유 사용자: 242,702명
- 고유 VOD: 166,159개
- 기간: 2025-01-01 ~ 2025-01-31
- director NULL: 19,037건 (실제 측정값)
- smry NULL: 28건

## 핵심 설계 결정사항

### 만족도(Satisfaction) 공식 - 베이지안 스코어
```
satisfaction = (v * R + m * C) / (v + m)
v=VOD별 시청건수, R=시청비율, C=전체평균(~0.47), m=5.0
60초 이하 시청 → satisfaction = 0.0
```

### 임베딩 전략
- 모델: paraphrase-multilingual-MiniLM-L12-v2 (384d, 한국어 지원, 무료)
- 입력: asset_nm + ct_cl + genre + genre_detail + director + cast_lead + smry
- 저장: pgvector HNSW 인덱스 (m=16, ef_construction=64)

## 파일 구조 (git)
```
lg2-ahreum/
├── database-design/
│   ├── schema/create_tables.sql        # users, vod, watch_history DDL
│   ├── schema/create_indexes.sql       # 16개 인덱스
│   ├── schema/create_extension_tables.sql  # vod_embedding 등
│   └── migration/migrate.sql           # 마이그레이션 스크립트
└── rag-pipeline-design/
    ├── pipeline/config.py              # DB/API 설정
    ├── pipeline/db.py                  # DB 연결 (비밀번호 프롬프트 포함)
    ├── pipeline/01_fill_missing.py     # TMDB API로 결측치 보완
    ├── pipeline/02_generate_embeddings.py  # 임베딩 생성 + pgvector 저장
    ├── schema/pgvector_setup.sql       # pgvector + HNSW 설정
    └── requirements.txt
```

## 환경 변수
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=vod_recommendation
DB_USER=postgres
DB_PASSWORD=  (실행 시 프롬프트로 입력)
TMDB_API_KEY=  (themoviedb.org에서 발급)
```
