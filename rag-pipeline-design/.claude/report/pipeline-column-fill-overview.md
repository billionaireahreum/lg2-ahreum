# VOD 메타데이터 보완 파이프라인 전체 개요

**작성일**: 2026-03-10
**브랜치**: `rag-pipeline-design`
**DB**: `vod_recommendation` / 메인 테이블: `vod` (166,159 row, 1개월 샘플)

---

## 1. 채우는 컬럼 한눈에 보기

| 컬럼 | 담당 스크립트 | 소스 | 현재 상태 |
|------|-------------|------|----------|
| `director` | 01_fill_missing.py | TMDB credits → person API | ✅ 완료 (90.7%) |
| `smry` | 01_fill_missing.py | TMDB overview → Ollama 폴백 | ✅ 완료 (100%) |
| `cast_lead` | 03_fill_cast_rating_date.py | TMDB credits billing 1~3위 | 🔄 진행 중 |
| `cast_guest` | 03_fill_cast_rating_date.py | TMDB credits billing 4~8위 | 🔄 진행 중 |
| `rating` | 03 → 04_fill_rating_kmdb.py | TMDB KR → TMDB US 매핑 → KMDB | 🔄 진행 중 |
| `release_date` | 03_fill_cast_rating_date.py | TMDB release_date / first_air_date | 🔄 진행 중 |
| `content_vector` | 02_generate_embeddings.py | paraphrase-multilingual-MiniLM-L12-v2 | ⚠️ 임시본 (재생성 예정) |

> **원본 데이터에서 이미 채워진 컬럼**: `disp_rtm` (100%), `series_nm` (99.7%), `asset_nm`, `genre`, `ct_cl` 등

---

## 2. Step 1 — director / smry 보완

**파일**: `pipeline/01_fill_missing.py`
**처리 단위**: row 단위 (1건씩)
**처리 조건**: `director IS NULL OR smry IS NULL AND rag_processed = FALSE`

### 동작 흐름

```
vod row 로드 (director IS NULL OR smry IS NULL)
    ↓
제목 정규화 (normalize_title)
  - [자막], (더빙), 1회, 시즌2, HD/UHD 등 제거
    ↓
TMDB 검색 (ko-KR)
  - ct_cl 기반 movie/tv 판별
  - 연도 일치 후보 우선 선택
  - 실패 시 반대 유형으로 재시도
    ↓
[director 채우기]
  - TMDB credits crew에서 Director / Series Director 추출
  - person API로 한국어 이름 조회 (캐시 적용)
  - TV의 경우 created_by도 참조
    ↓
[smry 채우기]
  - TMDB overview ko-KR 조회
  - 없으면 en-US 조회
  - 없으면 Ollama (llama3.1:8b) 로 생성 (폴백)
    ↓
UPDATE vod
  SET director = COALESCE(%s, director),   -- 기존값 보존
      smry     = COALESCE(%s, smry),
      rag_processed = TRUE,
      rag_source    = 'TMDB' | 'OLLAMA' | 'TMDB+OLLAMA',
      rag_processed_at = NOW()
WHERE full_asset_id = %s
```

### 결과

| 컬럼 | 채움률 | 비고 |
|------|--------|------|
| director | ~90.7% | TMDB에 없는 국내 콘텐츠는 NULL 유지 |
| smry | ~100% | Ollama 폴백으로 거의 모든 row 채움 |

### Rate Limit
- `sleep(0.25)` / row
- 인메모리 `PERSON_NAME_CACHE` (person_id → 한국어 이름)로 중복 API 호출 방지

---

## 3. Step 2 — 임베딩 생성

**파일**: `pipeline/02_generate_embeddings.py`
**처리 단위**: row 단위
**저장 테이블**: `vod_embedding` (vod와 별도)
**처리 조건**: `vod_embedding`에 아직 없는 row만 (`LEFT JOIN ... WHERE ve.vod_id_fk IS NULL`)

### 입력 텍스트 구성

```python
parts = [
    asset_nm,       # 제목
    ct_cl,          # 유형 (영화/TV드라마 등)
    genre,          # 장르
    genre_detail,   # 세부 장르
    "감독: {director}",   # 있을 때만
    "주연: {cast_lead}",  # 있을 때만
    smry,           # 줄거리
]
# rating은 임베딩 제외 (필터링 전용으로만 사용)
```

### 모델 및 저장 방식

| 항목 | 내용 |
|------|------|
| 모델 | `paraphrase-multilingual-MiniLM-L12-v2` |
| 차원 | 384d |
| 정규화 | L2 정규화 (`normalize_embeddings=True`) |
| 인덱스 | pgvector HNSW |
| 멱등성 | `ON CONFLICT (vod_id_fk, embedding_type) DO UPDATE` |

### 현재 상태 및 재생성 예정

- 166,159개 임베딩 생성 완료 (임시본)
- **단, 03번 완료 전 생성한 상태** → cast_lead, rating 등이 비어있는 상태로 임베딩됨
- **03번 + 04번 완료 후 재생성 예정**

---

## 4. Step 3 — cast / rating / release_date 보완

**파일**: `pipeline/03_fill_cast_rating_date.py`
**처리 단위**: **시리즈 단위** (normalized_title + ct_cl 기준 그룹핑)
**처리 조건**: `tmdb_id IS NULL AND is_active = TRUE AND ct_cl IN ('영화', 'TV드라마', 'TV애니메이션', '키즈', 'TV 연예/오락')`

### Row 단위 → 시리즈 단위로 전환한 이유

동일 콘텐츠가 더빙/자막/HD/UHD/제공사별로 N개 row로 분리됨.

```
겨울왕국 [4K]    → row 1개  ← 동일 콘텐츠
겨울왕국 [더빙]  → row 1개  ← 동일 콘텐츠
겨울왕국 (N사)   → row 20개 ← 동일 콘텐츠
```

| 방식 | 처리 단위 | API 호출 수 |
|------|----------|------------|
| 기존 (row 단위) | 141,957건 | ~425,871회 |
| 신규 (시리즈 단위) | 20,115개 | ~40,230회 |
| 절감 | — | **~85% 감소** |

### 동작 흐름

```
[DB] tmdb_id IS NULL 전체 로드 (141,957건)
    ↓
[Python] normalized_title + ct_cl 기준 시리즈 그룹핑
  → 20,115개 고유 시리즈 (85% 중복 제거)
    ↓
[각 시리즈 반복]
  1) 제목 정규화 (normalize_title)
     - [자막], (더빙), 1회, 시즌2, Season2, HD, UHD, 4K 제거
     - kiwipiepy 한국어 띄어쓰기 자동 교정
  2) TMDB 검색 (1회)
     - ct_cl에 '영화' 포함 → movie, 그 외 → tv
     - 완전 일치 → 포함 관계 → 첫 번째 결과 순 매칭
     - 실패 시 반대 유형(movie ↔ tv)으로 재시도
  3) 상세 조회 (1회, append_to_response)
     - 영화: /movie/{id}?append_to_response=credits,release_dates
     - TV:   /tv/{id}?append_to_response=credits,content_ratings
  4) 메타데이터 추출
     - cast_lead: billing order 1~3위
     - cast_guest: billing order 4~8위
     - rating: KR 직접값 → US 매핑 → NULL
     - release_date: release_date (영화) / first_air_date (TV)
  5) 동일 시리즈 모든 row 일괄 UPDATE
     WHERE full_asset_id = ANY([...])
```

### rating 추출 계층

```
영화:
  1순위 → TMDB KR release_dates.certification   → rating_source = 'tmdb_kr'
  2순위 → TMDB US MPAA 등급 → KR 매핑           → rating_source = 'tmdb_us'
    G     → 전체관람가
    PG    → 12세이상관람가
    PG-13 → 12세이상관람가
    R     → 15세이상관람가
    NC-17 → 청소년관람불가

TV:
  1순위 → TMDB KR content_ratings.rating        → rating_source = 'tmdb_kr'
  2순위 → TMDB US TV Parental Guidelines → KR 매핑 → rating_source = 'tmdb_us'
    TV-Y  → 전체관람가
    TV-Y7 → 7세이상관람가
    TV-G  → 전체관람가
    TV-PG → 12세이상관람가
    TV-14 → 15세이상관람가
    TV-MA → 청소년관람불가

3순위 → NULL 유지 (억지로 채우지 않음)
```

### 체크포인트 설계

| tmdb_id 값 | 의미 | 다음 실행 시 |
|------------|------|------------|
| `NULL` | 미처리 | 재처리 대상 |
| `-1` | TMDB 검색 실패 | 영구 제외 |
| `> 0` | 처리 완료 | 제외 |

### UPDATE 정책

```sql
SET
    tmdb_id         = {값},           -- 항상 덮어씀 (체크포인트)
    tmdb_media_type = {값},           -- 항상 덮어씀
    cast_lead       = COALESCE(cast_lead,    {새값}),  -- 기존값 보존
    cast_guest      = COALESCE(cast_guest,   {새값}),
    rating          = COALESCE(rating,       {새값}),
    rating_source   = COALESCE(rating_source,{새값}),
    release_date    = COALESCE(release_date, {새값}),
    tmdb_checked_at = NOW()
WHERE full_asset_id = ANY({시리즈 전체 id 목록})
```

### Rate Limit
- `sleep(0.26)` / API 호출
- TMDB 제한: 40회/10초 = 4회/초

### 현재 진행 상황 (2026-03-10 15:04 기준)

| 항목 | 수치 |
|------|------|
| 진행률 | 1,700 / 20,115 (8.5%) |
| TMDB 발견률 | 40.8% (TV 계열 우선 처리 중) |
| 예상 완료 | ~20:10 |

---

## 5. Step 4 — rating KMDB 보완 (예정)

**파일**: `pipeline/04_fill_rating_kmdb.py` (존재)
**처리 조건**: `ct_cl = 'TV드라마' AND (rating IS NULL OR rating_source = 'rule_based')`

| 항목 | 내용 |
|------|------|
| 소스 | KMDB Open API |
| 일일 제한 | 1,000회 |
| 대상 시리즈 | TV드라마 ~3,104개 |
| 예상 소요 | ~1~3일 (TMDB+rule_based 이후 남은 건만) |
| rating_source | `'kmdb'` |

---

## 6. Step 5 — rule-based rating 보완 (예정)

**03번 완료 후 NULL 잔량 확인 후 적용**

| ct_cl | 기본값 | rating_source |
|-------|--------|--------------|
| 키즈 / TV애니메이션 | 전체관람가 | rule_based |
| TV드라마 | 15세이상관람가 | rule_based |
| TV 연예/오락 | 12세이상관람가 | rule_based |
| 공포/범죄 키워드 포함 | 청소년관람불가 | rule_based |

> KMDB / 네이버 크롤링 결과가 오면 `rule_based` 값을 덮어씀 → 추적 가능

---

## 7. Step 6 — 임베딩 재생성 (예정)

**파일**: `pipeline/02_generate_embeddings.py` (수정 예정)
**시점**: Step 3~5 완료 후

- 현재 임베딩: cast_lead/rating이 빈 상태에서 생성된 임시본
- 재생성 시 입력 텍스트에 `cast_lead`, `smry` 등 풍부한 메타데이터 반영
- **시리즈 단위 22,414개만 연산** → 결과를 동일 시리즈 row 전체에 복사 (166,159번 → 22,414번)

---

## 8. source 우선순위 (rating 기준)

```
tmdb_kr  (최우선 — TMDB 한국 직접값)
  ↓
kmdb     (TMDB KR 없을 때 — 한국 공식 DB)
  ↓
tmdb_us  (KMDB도 없을 때 — TMDB US 매핑)
  ↓
naver_crawl  (TV 연예/오락 한정)
  ↓
rule_based   (마지막 안전망 — 언제든 더 좋은 source로 교체 가능)
```

---

## 9. 전체 파이프라인 실행 순서

```
01_fill_missing.py          ✅ 완료  (director, smry)
    ↓
02_generate_embeddings.py   ⚠️ 임시 완료 (재생성 예정)
    ↓
03_fill_cast_rating_date.py 🔄 진행 중 (cast, rating, release_date)
    ↓
04_fill_rating_kmdb.py      🔜 예정 (TV드라마 rating 정교화)
    ↓
rule_based UPDATE           🔜 예정 (NULL 잔량 일괄 처리)
    ↓
02_generate_embeddings.py   🔜 재생성 (최종 메타데이터 반영)
```

---

## 10. 컬럼별 최종 채움 목표

| 컬럼 | 목표 채움률 | 전략 |
|------|-----------|------|
| director | 90%+ | TMDB (이미 완료) |
| smry | 100% | TMDB + Ollama (이미 완료) |
| cast_lead | 60~70% | TMDB (영화/해외 위주) |
| cast_guest | 60~70% | TMDB |
| rating | 80%+ | TMDB + KMDB + rule_based |
| release_date | 65%+ | TMDB |
| content_vector | 100% | 임베딩 재생성 후 |
