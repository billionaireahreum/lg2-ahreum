# LG헬로비전 VOD 추천 시스템 - Phase 1~2 전체 파이프라인 보고서

**작성일**: 2026-03-09
**담당**: 박아름 (RAG), 황대원 (DB)
**대상 브랜치**: `database-design`, `rag-pipeline-design`
**상태**: 완료

---

## 1. 전체 흐름 요약

```
[원본 CSV 3종]
       ↓ Phase 1 (database-design)
[PostgreSQL 정규화 DB]
       ↓ Phase 2 (rag-pipeline-design)
[결측치 보완 + 벡터 임베딩 생성]
       ↓
[추천 시스템 준비 완료]
```

---

## 2. Phase 1 - DB 설계 및 마이그레이션

### 2-1. 원본 데이터 (CSV 3종)

| 파일 | 내용 | 규모 |
|------|------|------|
| `user_table.csv` | 사용자 정보 | 242,702명 |
| `vod_table.csv` | VOD 메타데이터 | 166,159개 |
| `watch_history_table.csv` | 시청 이력 | 3,992,530건 |

**데이터 기간**: 2025-01-01 ~ 2025-01-31 (1개월)

---

### 2-2. 스테이징 → 정규화 테이블 변환

CSV를 PostgreSQL에 스테이징 테이블로 로드한 후, 정규화된 테이블로 마이그레이션했습니다.

#### users 테이블 변환
| 원본 컬럼 | 변환 내용 |
|-----------|-----------|
| `AGE_GRP10` | 소문자 컬럼명으로 변환 |
| `INHOME_RATE` | TEXT `'50.0'` → SMALLINT `50` |
| `CH_HH_AVG_MONTH1` | TEXT → NUMERIC(반올림 2자리) |
| `NFX_USE_YN` | `'Y'`/`'N'` → BOOLEAN |

#### vod 테이블 변환
| 원본 값 | 변환 내용 |
|---------|-----------|
| `director = '-'` | NULL로 변환 |
| `director = 'nan'` | NULL로 변환 |
| 빈 문자열 | NULL로 변환 (genre, smry 등) |
| `disp_rtm_sec = '4860.0'` | INTEGER `4860`으로 변환 |

**결과**: director NULL **19,037건**, smry NULL **28건**

> ⚠️ 초기 계획서에 "313건"으로 잘못 기재되었으나, 실제 측정값은 19,037건이었음.
> 원인: 계획서 작성 시 샘플 데이터 기준으로 추정한 수치였음.

#### watch_history 테이블 변환
| 원본 값 | 변환 내용 |
|---------|-----------|
| `strt_dt` TEXT | TIMESTAMP 캐스팅 |
| `use_tms = '411.0'` | INTEGER `411`로 변환 |
| `completion_rate` | NUMERIC(8,4) 반올림 |
| `satisfaction` | NUMERIC(8,4) 반올림 |

**FK 무결성**: users/vod에 없는 레코드 자동 제외 (`WHERE EXISTS`)
**중복 처리**: `ON CONFLICT DO NOTHING`

---

### 2-3. 최종 DB 구조

```
users (242,702행)
  └── watch_history (3,992,530행) ──→ vod (166,159행)
                                        └── vod_embedding (166,159행)
```

#### 핵심 설계 결정

**만족도(Satisfaction) 공식 - 베이지안 스코어**
```
satisfaction = (v × R + m × C) / (v + m)
  v: VOD별 시청 건수
  R: 시청 비율 (use_tms / disp_rtm_sec)
  C: 전체 평균 시청 비율 (~0.47)
  m: 신뢰도 조절 파라미터 (기본값 5.0)
  60초 이하 시청 → satisfaction = 0.0
```

**RAG 추적 컬럼 (vod 테이블에 추가)**
```sql
rag_processed    BOOLEAN DEFAULT FALSE
rag_source       VARCHAR(64)     -- 'TMDB' | 'OLLAMA'
rag_processed_at TIMESTAMP
```

---

## 3. Phase 2 - RAG 파이프라인

### 3-1. Step 1: 결측치 보완 (`01_fill_missing.py`)

#### 처리 대상
| 컬럼 | NULL 건수 | 비율 |
|------|-----------|------|
| director | 19,037건 | 11.5% |
| smry | 28건 | 0.02% |

#### 처리 방식 (TMDB API)

```
VOD 제목 (asset_nm)
       ↓
  ct_cl 기반 movie/tv 판별
       ↓
  TMDB Search API 검색
       ↓ 성공
  TMDB Credits API → 감독명 추출
  TMDB Overview → 줄거리 추출
       ↓ 실패
  director = NULL 유지 (억지 추론 방지)
```

**처리 결과**

| 항목 | 수치 |
|------|------|
| 전체 처리 건수 (rag_processed=TRUE) | 19,049건 |
| TMDB 처리 | 19,040건 |
| Ollama 처리 (폴백) | 9건 |
| director 채움 성공 | **3,571건** |
| director 여전히 NULL | **15,478건** |
| smry 채움 | **28건 (100%)** |

**smry(줄거리)는 100% 채움 완료.**

#### director 15,478건이 여전히 NULL인 이유
1. 한국 케이블 TV 콘텐츠 → TMDB에 등록 자체가 없음
2. 제목 정규화 미적용 → `[자막]`, `시즌2`, `(1부)` 등이 붙은 채로 검색하여 매칭 실패
3. `_normalize_title()` 함수가 최종 파이프라인에서 누락됨

---

### 3-2. Step 2: 임베딩 생성 (`02_generate_embeddings.py`)

#### 임베딩 텍스트 구성 방식
```python
text = f"{asset_nm} {ct_cl} {genre} {genre_detail} 감독: {director} 주연: {cast_lead} {smry}"
```

#### 모델
| 항목 | 내용 |
|------|------|
| 모델 | `paraphrase-multilingual-MiniLM-L12-v2` |
| 차원 | 384d |
| 정규화 | L2 정규화 (normalize_embeddings=True) |
| 이유 | 무료, 로컬 실행, 한국어+영어 혼용 지원 |

#### 저장 방식
- 테이블: `vod_embedding`
- 인덱스: pgvector HNSW (m=16, ef_construction=64)
- 유사도: cosine similarity (`<=>` 연산자)
- 배치 크기: 256건씩

#### 처리 결과
| 항목 | 수치 |
|------|------|
| 전체 VOD | 166,159개 |
| 임베딩 완료 | **166,159개 (100%)** |
| 평균 vector magnitude | 1.0 (L2 정규화) |

---

## 4. 현재 DB 결측값 현황

```sql
-- 2026-03-09 기준
total   : 166,159
missing_title       :      0 (0%)     ✅
missing_genre       :      1 (~0%)    ✅
missing_director    : 15,478 (9.3%)   ⚠️
missing_cast_lead   : 166,159 (100%)  ⬜ 원본 없음
missing_smry        :      0 (0%)     ✅
missing_rating      : 166,159 (100%)  ⬜ 원본 없음
missing_release_date: 166,159 (100%)  ⬜ 원본 없음
missing_embedding   :      0 (0%)     ✅
```

**cast_lead / rating / release_date**: 원본 CSV에 없던 데이터.
DB 설계 단계에서 향후 채울 것을 가정하고 컬럼만 미리 생성함.

---

## 5. 소스별 처리 현황

| rag_source | 건수 | 비고 |
|------------|------|------|
| NULL | 147,110 | RAG 미처리 (원래부터 director/smry 있던 VOD) |
| TMDB | 19,040 | TMDB API로 처리 |
| OLLAMA | 9 | Ollama llama3.1:8b 폴백 처리 |

---

## 6. 알려진 이슈 및 한계

### 이슈 1: director 15,478건 미채움 (9.3%)
- **원인**: 한국 케이블 콘텐츠의 TMDB 등록 부재 + 제목 정규화 미적용
- **해결 방법**: `_normalize_title()` 재적용 후 재처리, 또는 Ollama/다른 LLM 활용
- **우선순위**: 중간 (추천 시스템 동작에는 지장 없음)

### 이슈 2: cast_lead / rating / release_date 100% 결측
- **원인**: 원본 CSV에 해당 데이터 없음
- **해결 방법**: TMDB API로 채울 수 있으나, 파이프라인 추가 개발 필요
- **우선순위**: 낮음 (임베딩에 cast_lead 반영 시 품질 향상 가능)

### 이슈 3: 계획서 수치 오류
- 초기 계획서: director NULL 313건
- 실제: 19,037건
- **원인**: 계획서 작성 시 샘플 데이터 기준 추정

---

## 7. 다음 단계 권장사항

| Phase | 작업 | 담당 |
|-------|------|------|
| Phase 3 | watch_history + vod_embedding 기반 Matrix Factorization 추천 엔진 | 최기문 |
| Phase 4 | FastAPI + LG Exaone 4.0 감성 문구 생성 | 이가원 |
| Phase 5 | Streamlit UI | 신정윤 |
| Phase 6 | YOLOv8 영상인식 마켓플레이스 | 박아름+최기문 |

**Phase 3 시작 전 확인 필요:**
```sql
-- 임베딩 확인
SELECT COUNT(*) FROM vod_embedding;  -- 166,159 확인

-- 시청 이력 확인
SELECT COUNT(*) FROM watch_history;  -- 3,992,530 확인
```
