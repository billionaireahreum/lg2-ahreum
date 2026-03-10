# Phase 3 TMDB 메타데이터 보완 파이프라인 — 시리즈 단위 재설계 보고서

**작업 일시**: 2026-03-10 (오전~오후, 계속 진행 중)
**작성일**: 2026-03-10
**브랜치**: `rag-pipeline-design`
**파일**: `pipeline/03_fill_cast_rating_date.py` (완전 재작성)

---

## 1. 오늘 작업 요약

| 항목 | 내용 |
|------|------|
| 핵심 결정 | row 단위 파이프라인 폐기 → 시리즈 단위로 완전 전환 |
| 코드 변경 | `03_fill_cast_rating_date.py` 전면 재작성 |
| DB 변경 | `vod` 테이블에 컬럼 3개 추가 |
| 스크립트 실행 | 14:27 시작, 131,226 row / 19,537 고유 시리즈 확인 |

---

## 2. 전환 배경 — row 단위 방식의 한계

기존 `03_fill_cast_rating_date.py` (v4)는 `tmdb_checked_at IS NULL` 기준으로 row를 1건씩 처리했다.
`vod` 테이블의 구조적 특성을 고려하면 이 방식은 근본적으로 비효율적이었다.

### 문제의 본질

`vod` 테이블은 **서비스 제공 단위** row다. 동일 콘텐츠가 화질·자막·더빙·제공사별로 N개 row로 분리된다.

```
겨울왕국 [4K]     → row 1개  ← 동일 콘텐츠
겨울왕국 [더빙]   → row 1개  ← 동일 콘텐츠
겨울왕국 [자막]   → row 1개  ← 동일 콘텐츠
겨울왕국 (N사)    → row 20개 ← 동일 콘텐츠
```

→ 겨울왕국 1편에 TMDB API를 23번 호출하는 구조.
→ 인메모리 캐싱으로 완화했지만, **세션 재시작 시 캐시 소멸** → 재호출 발생.
→ 근본 해결이 불가능한 구조적 문제.

### 수치로 본 낭비

| 구분 | 처리 대상 | API 호출 |
|------|----------|---------|
| row 단위 (기존) | 131,226건 | ~110,507회 (캐싱 적용 후 추정) |
| 시리즈 단위 (신규) | 19,537개 | ~19,537회 (시리즈당 2회: 검색+상세) |
| 절감 | — | **~5.7배 감소** |

---

## 3. 아키텍처 최종 결정 (GPT·Gemini 의견 수렴 후)

여러 AI 의견을 수렴한 결과 아래와 같이 확정했다.

### 채택한 것

| 항목 | 이유 |
|------|------|
| 시리즈 단위 처리 (normalized_title 기준) | 핵심 효율화 |
| `tmdb_id` DB 영구 저장 | 세션 재시작 시 재호출 방지 |
| `tmdb_id = -1` 검색 실패 표시 | 재호출 무한루프 방지 |
| `tmdb_media_type` 저장 | movie/tv 구분 영구 기록 |
| `append_to_response` 활용 | 상세 조회 1회로 credits+등급 동시 수집 |
| rating 계층형 보완 (KR → US 매핑) | TMDB KR 등급 부재 대응 |
| `rating_source` 컬럼 저장 | 등급 출처 추적 (tmdb_kr/tmdb_us/rule_based) |

### 버린 것

| 항목 | 이유 |
|------|------|
| `content_master` 신규 테이블 | vod 직접 활용으로 충분, 불필요한 복잡도 |
| `asyncio/aiohttp` 비동기 처리 | 19,537건은 동기 처리로 ~4시간 내 완료 가능 |
| `rating_confidence` 수치화 | 복잡도 대비 실용성 낮음 |
| `metadata_version`, `tmdb_match_method` | 현 단계 오버엔지니어링 |
| `normalized_title` 컬럼 저장 | 스크립트에서 계산하면 충분 |

---

## 4. DB 스키마 변경

스크립트 최초 실행 시 자동으로 3개 컬럼이 추가된다.

```sql
-- 2026-03-10 14:27 자동 추가 완료
ALTER TABLE vod ADD COLUMN tmdb_id         INT;
-- NULL=미처리, -1=TMDB 미발견, >0=TMDB ID

ALTER TABLE vod ADD COLUMN tmdb_media_type TEXT;
-- 'movie' / 'tv'

ALTER TABLE vod ADD COLUMN rating_source   TEXT;
-- 'tmdb_kr' / 'tmdb_us' / 'rule_based'
```

기존 `tmdb_checked_at` 컬럼은 그대로 유지 (작업 시각 기록용).

---

## 5. 신규 파이프라인 동작 방식

### 5-1. 전체 흐름

```
[DB] tmdb_id IS NULL 인 row 전체 로드 (131,226건)
        ↓
[Python] normalized_title 기준으로 시리즈 그룹핑
        → 19,537개 고유 시리즈 도출
        ↓
[각 시리즈 반복]
  TMDB 검색 (1회)
        ↓ 발견
  TMDB 상세 조회 (1회, append_to_response)
  └── credits (cast_lead, cast_guest)
  └── release_dates / content_ratings (rating)
  └── release_date / first_air_date
        ↓
  같은 시리즈 모든 row 일괄 UPDATE (WHERE full_asset_id = ANY([...]))
        ↓ 미발견
  tmdb_id = -1 기록 → 재호출 영구 차단
```

### 5-2. 제목 정규화 로직

```python
normalize_title("겨울왕국 [4K][더빙]")  → "겨울왕국"
normalize_title("오징어 게임 시즌2")    → "오징어 게임"
normalize_title("이상한변호사우영우15회") → "이상한 변호사 우영우"
```

제거 대상: `[자막]`, `(더빙)`, `1회`, `1부`, `시즌2`, `Season2`, `HD`, `UHD`, `4K`
추가 처리: `kiwipiepy` 한국어 띄어쓰기 자동 교정

정규화 결과는 **DB에 저장하지 않음** — 스크립트 내부에서만 사용.

### 5-3. TMDB 검색 전략

```
1차: ct_cl 기반 유형 결정 (영화 포함 → movie, 그 외 → tv)
2차: 원제목으로 검색

매칭 우선순위:
  1) 완전 일치 (공백 무시)
  2) 포함 관계
  3) 첫 번째 결과 폴백

실패 시: 반대 유형(movie↔tv)으로 재시도
```

### 5-4. append_to_response 활용

```
기존 방식: 검색(1회) + credits(1회) + 등급(1회) = 3회/시리즈
신규 방식: 검색(1회) + 상세+credits+등급(1회) = 2회/시리즈
```

```
영화: /movie/{id}?append_to_response=credits,release_dates
TV:   /tv/{id}?append_to_response=credits,content_ratings
```

### 5-5. 등급(rating) 계층형 추출

```
1순위: TMDB KR 직접값 → rating_source = 'tmdb_kr'
2순위: TMDB US 등급 → KR 매핑 → rating_source = 'tmdb_us'

US 영화 매핑:
  G      → 전체관람가
  PG     → 12세이상관람가
  PG-13  → 12세이상관람가
  R      → 15세이상관람가
  NC-17  → 청소년관람불가

US TV 매핑:
  TV-Y   → 전체관람가
  TV-Y7  → 7세이상관람가
  TV-G   → 전체관람가
  TV-PG  → 12세이상관람가
  TV-14  → 15세이상관람가
  TV-MA  → 청소년관람불가

3순위: NULL 유지 (억지로 채우지 않음)
→ rule_based 보완은 별도 스크립트로 처리 예정
```

### 5-6. UPDATE 정책

```sql
-- tmdb_id, tmdb_media_type, rating_source: 항상 덮어씀 (체크포인트)
-- cast_lead, cast_guest, rating, release_date: COALESCE — 기존값 보존
SET
    tmdb_id         = {값},
    tmdb_media_type = {값},
    cast_lead       = COALESCE(cast_lead,    {새값}),  -- 기존값 우선
    cast_guest      = COALESCE(cast_guest,   {새값}),
    rating          = COALESCE(rating,       {새값}),
    rating_source   = COALESCE(rating_source,{새값}),
    release_date    = COALESCE(release_date, {새값}),
    tmdb_checked_at = NOW()
WHERE full_asset_id = ANY({시리즈 전체 id 목록})
```

### 5-7. 체크포인트 설계

| tmdb_id 값 | 의미 | 다음 실행 시 |
|------------|------|-------------|
| `NULL` | 미처리 | 재처리 대상 |
| `-1` | TMDB 검색 실패 | 영구 제외 (재호출 방지) |
| `> 0` | 처리 완료 | 제외 |

---

## 6. 실행 결과 (2026-03-10 14:27 기준)

```
14:27:18 [INFO] === 시리즈 단위 메타데이터 보완 시작 (TMDB append_to_response) ===
14:27:18 [INFO] 컬럼 추가 완료: vod.tmdb_id INT
14:27:18 [INFO] 컬럼 추가 완료: vod.tmdb_media_type TEXT
14:27:18 [INFO] 컬럼 추가 완료: vod.rating_source TEXT
14:27:18 [INFO] 미처리 row 로딩 중...
14:27:23 [INFO] 총 미처리 row: 131,226건 → 고유 시리즈: 19,537개 (그룹핑 완료)
```

| 항목 | 수치 |
|------|------|
| 미처리 row | 131,226건 |
| 고유 시리즈 | 19,537개 |
| 그룹핑 압축률 | 131,226 → 19,537 (**85% 중복 제거**) |
| 예상 API 호출 수 | ~39,074회 (시리즈당 검색+상세 2회) |
| 예상 소요 시간 | ~2.8시간 (0.26초/호출 × 39,074회) |

> 처리 중 (14:37 재시작) — 완료 시 결과 업데이트 예정

### 진행 경과 (2026-03-10 오후)

| 시각 | 진행 | 발견률 | cast | rating(KR) | date | API |
|------|------|--------|------|-----------|------|-----|
| 14:40 | 200 (1.0%) | 31.0% | 39 | 20 | 61 | 402 |
| 15:08 | 2,000 (9.9%) | 41.7% | 717 | 468 | 830 | 4,021 |
| 15:39 | 4,000 (19.9%) | 47.1% | 1,759 | 1,265 | 1,882 | 8,032 |

- 발견률이 초반 31% → 47%로 상승 중 (영화 구간 진입할수록 증가 예상)
- 예상 완료: **2026-03-10 19:55 전후**

---

## 7. 기존 방식 대비 개선 요약

| 항목 | 기존 (row 단위, v4) | 신규 (시리즈 단위) |
|------|-------------------|-----------------|
| API 호출 수 | ~110,507회 | ~39,074회 |
| 캐시 지속성 | 인메모리 (세션 종료 시 소멸) | DB 영구 저장 |
| 재시작 안전성 | tmdb_checked_at 기준 | tmdb_id 기준 (명확) |
| 검색 실패 추적 | 불가 (NULL과 구분 불가) | tmdb_id = -1 명시 |
| rating 출처 추적 | 불가 | rating_source 컬럼 |
| 코드 구조 | row 1건씩 순차 | 시리즈 그룹 일괄 처리 |

---

## 8. 다음 단계

| 순서 | 작업 | 파일 | 상태 |
|------|------|------|------|
| 1 | 03번 완료 대기 | `03_fill_cast_rating_date.py` | 🔄 진행 중 |
| 2 | rule-based rating 보완 | `04_fill_rating_kmdb.py` (또는 별도) | 🔜 예정 |
| 3 | 임베딩 재생성 | `02_generate_embeddings.py` 수정 | 🔜 예정 |

### 임베딩 재생성 계획 (Step 3 완료 후)
- 시리즈 단위 22,414개만 임베딩 연산 (166,159번 → 22,414번)
- 연산 결과를 같은 시리즈 row 전체에 복사
- 입력 텍스트: `제목 / 유형 / 장르 / 감독 / 주연(cast_lead) / 조연(cast_guest) / 줄거리 / 개봉연도`
- **cast_guest도 임베딩에 포함 확정** (2026-03-10, 기존 임시본에서 누락되었던 항목)
- rating은 임베딩 본문 제외 (필터링 전용)

---

## 9. Git 이력

| 항목 | 내용 |
|------|------|
| 커밋 | `0d4ecb0` Rewrite 03 pipeline to series-based with TMDB append_to_response |
| PR | #3 머지 완료 (rag-pipeline-design → master, 2026-03-10) |
| ct_cl 오류 수정 | `TV연예오락` → `TV 연예/오락` (실제 DB값 확인 후 수정) |
