# Phase 3 TMDB 메타데이터 보완 파이프라인 진행 보고서

**작성일**: 2026-03-09
**브랜치**: `rag-pipeline-design`
**파일**: `pipeline/03_fill_cast_rating_date.py`

---

## 1. 목표

`vod` 테이블에서 비어 있는 4개 컬럼을 TMDB API로 채우는 배치 파이프라인 구축.

| 컬럼 | 설명 |
|------|------|
| `cast_lead` | billing order 상위 3명 (대표 출연진) |
| `cast_guest` | billing order 4~8위 (additional/supporting cast) |
| `rating` | 한국 시청 등급 (전체/12세/15세/청불) |
| `release_date` | 개봉일 또는 첫 방영일 |

**처리 대상**: `ct_cl IN ('영화', 'TV드라마', 'TV애니메이션')`, `is_active = TRUE`
**총 대상 규모**: 약 110,507건

---

## 2. 멱등성 설계

- `tmdb_checked_at IS NULL` 조건으로 미처리 건만 조회
- TMDB 매칭 성공/실패 관계없이 처리 후 `tmdb_checked_at = NOW()` 기록
- 재실행 시 기처리 건 자동 스킵 → 중단 후 이어받기 가능

---

## 3. 파이프라인 버전 히스토리

### v1 — 초기 구현
- row마다 TMDB search → credits → rating 순차 호출
- `time.sleep(0.26)` row당 1회 고정
- **문제**: 드라마 50화 = 동일 TMDB API 150번 호출 (중복)

### v2 — 인메모리 캐싱 도입 (`a7484e2`)
- `_SEARCH_CACHE`, `_CREDITS_CACHE`, `_RATING_CACHE` 3개 딕셔너리 추가
- 같은 제목/tmdb_id 재호출 방지
- **문제**: 캐시 히트 판정이 `len(_SEARCH_CACHE)` 크기 변화로 간접 추론 → 부정확

### v3 — `_tmdb_get()` 래퍼 + 정확한 카운터 (`d4235c5`)
- `_tmdb_get()` 공통 래퍼: 실제 API 호출 시에만 `sleep(0.26)` + `_API_CALL_COUNT++`
- 캐시 히트 카운터 분리: `_SEARCH_CACHE_HIT`, `_CREDITS_CACHE_HIT`, `_RATING_CACHE_HIT`
- 가짜 `is_cache_hit` 로직 제거
- **해결**: rate limit 제어가 실제 API 호출 기준으로 정확해짐

### v4 — DB 커넥션 배치 재사용 (`a550c19`) ← 현재
- `fetch_unprocessed(conn, batch_size)` / `update_vod(cur, ...)` 로 커넥션 파라미터화
- `run()`에서 `get_conn()` 1회만 열고 전체 루프에서 재사용
- 100건마다 `conn.commit()` (장애 시 손실 최소화)
- 로그에 캐시 딕셔너리 크기 추가: `search캐시:87(117)` 형태

---

## 4. 현재 성능 수치

### 세션 1 (최적화 전, v1)
> 2026-03-09 17:01 ~ 17:28 (약 27분)

| 누적 처리 | cast 채움률 | rating 채움률 | 미발견률 | 속도 |
|-----------|------------|--------------|---------|------|
| 1,800건 | 58.5% | 36.3% | 41.5% | ~43건/분 |

### 세션 2 (최적화 전, v1 이어받기)
> 2026-03-09 20:23 ~ 21:44 (약 81분)

| 누적 처리 | cast 채움률 | rating 채움률 | 미발견률 | 속도 |
|-----------|------------|--------------|---------|------|
| 4,200건 | 62.3% | 47.4% | 36.9% | ~43건/분 |

### 세션 3 (v4 캐싱+DB 최적화 적용)
> 2026-03-09 22:29 ~ (진행 중)

| 누적 처리 | cast 채움률 | rating 채움률 | 미발견률 | 속도 |
|-----------|------------|--------------|---------|------|
| 300건 | **76%** | 44.3% | 24% | **~86건/분** |

**캐싱 효과 (300건 기준):**

| 항목 | 수치 |
|------|------|
| 실제 API 호출 | 380건 (캐싱 없었으면 ~900건) |
| API 호출 절감률 | **~58%** |
| credits 캐시 히트 | 213건 (고유 tmdb_id 15개만 사용) |
| 속도 향상 | 기존 대비 **약 2배** |

---

## 5. 핵심 설계 결정

### 제목 정규화 전략
- 원제목 우선 검색 → 실패 시 정규화 제목 시도
- 정규화: `[자막]`, `(더빙)`, `1회`, `시즌2` 등 제거 + `kiwipiepy` 한국어 띄어쓰기 교정
- 검색 실패 시 영화↔TV 교차 시도

### TMDB 매칭 전략
- 결과 상위 5개 중 완전 일치 → 포함 관계 → 첫 번째 결과 순으로 선택

### cast_guest 의미 재정의
- TMDB episode-level `guest_stars`와 **다른 개념**
- billing order 4~8위 = additional/supporting cast (추가 출연진)
- 드라마 회차별 게스트 배우가 아닌, 시리즈 레벨 메타보강용 필드

---

## 6. 남은 작업

### 즉시 진행 가능
| 작업 | 파일 | 상태 |
|------|------|------|
| TMDB 파이프라인 완료 | `03_fill_cast_rating_date.py` | 🔄 진행 중 (~104,000건 남음) |
| KMDB API 신청 | — | 🕐 승인 대기 (1~2일) |

### TMDB 완료 후
| 작업 | 설명 |
|------|------|
| KMDB 폴백 파이프라인 | `04_fill_rating_kmdb.py` — 한국 영화 rating/director 보강 |
| 예능 메타 파이프라인 | `04_fill_domestic_program_meta.py` — 네이버 크롤링으로 TV 연예/오락 cast 채우기 |
| 영문 배우명 보완 | TMDB person API로 한글 이름 재조회 (Ha Jae-sook → 하재숙) |

### 장기 과제
- TV 에피소드 레벨 guest_stars 추출 (시즌/회차 식별 필요)
- 키즈/우리동네 장르 별도 전략 수립

---

## 7. 데이터 품질 이슈

| 이슈 | 원인 | 조치 |
|------|------|------|
| 영문 배우명 (Ha Jae-sook 등) | TMDB 한국어 번역 미등록 | TMDB person API 재조회로 보완 가능 |
| 한자 배우명 (翟天臨 등) | 중국 드라마 원어 그대로 | 정상 동작 |
| rating NULL | TMDB KR 등급 데이터 없음 | KMDB API 보완 예정 |
| TMDB 미발견 (~36%) | 한국 케이블/로컬 콘텐츠 TMDB 미등재 | 장르별 별도 소스 전략 필요 |

---

## 8. 아키텍처 결론

```
ct_cl = 영화/TV드라마/TV애니메이션
    → TMDB API (03_fill_cast_rating_date.py)  ← 현재 진행 중
    → KMDB API 폴백 (04_fill_rating_kmdb.py)  ← 예정

ct_cl = TV 연예/오락
    → 네이버 크롤링 (04_fill_domestic_program_meta.py)  ← 예정

ct_cl = 키즈 (해외)
    → TMDB 시도 가능

ct_cl = 키즈 (국내), 우리동네
    → 내부 메타 / rule-based 추출  ← 장기 과제
```
