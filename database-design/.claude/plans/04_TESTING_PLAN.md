# Plan 04 - 검증 및 테스트 계획

**목표**: 마이그레이션 결과의 데이터 정합성, 성능, 정규화 검증
**우선순위**: 필수 (Phase 4)
**선행 조건**: 마이그레이션 완료, 인덱스 생성 완료

---

## 1. 검증 체크리스트

### 1.1 데이터 정합성
- [ ] 행 수 확인 (기대값 대비)
- [ ] FK 참조 무결성 (위반 0건)
- [ ] NULL 비율 (허용된 컬럼만 NULL)
- [ ] 중복 행 없음
- [ ] satisfaction 분포 (설계요구사항.md 기준값 일치)
- [ ] completion_rate 범위 (0.0 ~ 1.0)

### 1.2 성능
- [ ] 사용자별 조회: < 100ms
- [ ] VOD별 조회: < 100ms
- [ ] 날짜 범위 조회: < 500ms
- [ ] 만족도 상위 조회: < 200ms
- [ ] 모든 인덱스 사용 확인 (Seq Scan 없음)

### 1.3 정규화
- [ ] 1NF: 모든 컬럼이 원자값
- [ ] 2NF: 부분 함수 종속 없음
- [ ] 3NF: 이행 함수 종속 없음

---

## 2. 데이터 정합성 검증 쿼리

### 2.1 행 수 확인

```sql
-- 기대: users ~242,702 / vod ~166,159 / watch_history ~3,992,530
SELECT
    'users'         AS table_name,
    COUNT(*)        AS row_count,
    242702          AS expected
FROM users
UNION ALL
SELECT 'vod', COUNT(*), 166159 FROM vod
UNION ALL
SELECT 'watch_history', COUNT(*), 3992530 FROM watch_history;
```

### 2.2 FK 무결성

```sql
-- watch_history → users FK 위반 확인
SELECT COUNT(*) AS orphan_users
FROM watch_history wh
WHERE NOT EXISTS (
    SELECT 1 FROM users u WHERE u.sha2_hash = wh.user_id_fk
);

-- watch_history → vod FK 위반 확인
SELECT COUNT(*) AS orphan_vods
FROM watch_history wh
WHERE NOT EXISTS (
    SELECT 1 FROM vod v WHERE v.full_asset_id = wh.vod_id_fk
);

-- 기대: 두 쿼리 모두 0
```

### 2.3 NOT NULL 제약 확인

```sql
-- users 필수 컬럼
SELECT
    COUNT(*) FILTER (WHERE sha2_hash IS NULL) AS sha2_null,
    COUNT(*) FILTER (WHERE nfx_use_yn IS NULL) AS nfx_null,
    COUNT(*) FILTER (WHERE created_at IS NULL) AS created_null
FROM users;

-- vod 필수 컬럼
SELECT
    COUNT(*) FILTER (WHERE full_asset_id IS NULL) AS id_null,
    COUNT(*) FILTER (WHERE asset_nm IS NULL) AS nm_null,
    COUNT(*) FILTER (WHERE ct_cl IS NULL) AS ctcl_null,
    COUNT(*) FILTER (WHERE disp_rtm_sec IS NULL) AS dur_null
FROM vod;

-- watch_history 필수 컬럼
SELECT
    COUNT(*) FILTER (WHERE user_id_fk IS NULL) AS user_null,
    COUNT(*) FILTER (WHERE vod_id_fk IS NULL) AS vod_null,
    COUNT(*) FILTER (WHERE strt_dt IS NULL) AS strt_null,
    COUNT(*) FILTER (WHERE use_tms IS NULL) AS tms_null,
    COUNT(*) FILTER (WHERE completion_rate IS NULL) AS cr_null,
    COUNT(*) FILTER (WHERE satisfaction IS NULL) AS sat_null
FROM watch_history;
```

### 2.4 결측치 현황 (허용 컬럼)

```sql
-- vod 결측치 (RAG 처리 예정)
SELECT
    COUNT(*) FILTER (WHERE director IS NULL) AS director_null,
    COUNT(*) FILTER (WHERE smry IS NULL) AS smry_null,
    COUNT(*) FILTER (WHERE cast_lead IS NULL) AS cast_null,
    COUNT(*) AS total
FROM vod;

-- 기대: director ~313건(0.01%), smry ~28건(0.00%)
```

### 2.5 satisfaction 분포 검증

```sql
-- 설계요구사항.md 기준값과 비교
SELECT
    COUNT(*) FILTER (WHERE satisfaction = 0)                AS zero_sat,        -- 기대: ~1,006,961
    COUNT(*) FILTER (WHERE satisfaction > 0 AND satisfaction <= 0.2) AS low_sat, -- 기대: ~653,230
    COUNT(*) FILTER (WHERE satisfaction > 0.2 AND satisfaction <= 0.6) AS mid_sat, -- 기대: ~766,208
    COUNT(*) FILTER (WHERE satisfaction > 0.6)              AS high_sat,        -- 기대: ~1,566,131
    ROUND(AVG(satisfaction)::numeric, 4)                    AS avg_sat,         -- 기대: 0.443
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY satisfaction)::numeric, 4) AS median_sat, -- 기대: 0.354
    ROUND(STDDEV(satisfaction)::numeric, 4)                 AS std_sat          -- 기대: 0.401
FROM watch_history;
```

### 2.6 completion_rate 범위 검증

```sql
-- completion_rate는 0.0 ~ 1.0 범위여야 함
SELECT
    COUNT(*) FILTER (WHERE completion_rate < 0) AS below_zero,
    COUNT(*) FILTER (WHERE completion_rate > 1) AS above_one,
    MIN(completion_rate) AS min_cr,
    MAX(completion_rate) AS max_cr,
    AVG(completion_rate) AS avg_cr  -- 기대: ~0.468
FROM watch_history;
```

### 2.7 중복 행 확인

```sql
-- users 중복 확인
SELECT COUNT(*) - COUNT(DISTINCT sha2_hash) AS user_duplicates
FROM users;

-- vod 중복 확인
SELECT COUNT(*) - COUNT(DISTINCT full_asset_id) AS vod_duplicates
FROM vod;

-- watch_history 중복 확인 (UNIQUE 제약 기준)
SELECT COUNT(*) AS duplicate_sessions
FROM (
    SELECT user_id_fk, vod_id_fk, strt_dt, COUNT(*) AS cnt
    FROM watch_history
    GROUP BY user_id_fk, vod_id_fk, strt_dt
    HAVING COUNT(*) > 1
) t;
```

---

## 3. 성능 테스트

### 3.1 실행 방법

```bash
# psql에서 타이밍 측정
psql -d vod_recommendation -c "\timing on" -f schema/performance_test.sql
```

### 3.2 테스트 케이스

```sql
\timing on

-- [TEST 1] 사용자별 시청이력 조회 (목표: < 100ms)
EXPLAIN (ANALYZE, BUFFERS)
SELECT wh.strt_dt, wh.use_tms, wh.completion_rate, wh.satisfaction,
       v.asset_nm, v.genre
FROM watch_history wh
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE wh.user_id_fk = (SELECT sha2_hash FROM users LIMIT 1)
ORDER BY wh.strt_dt DESC
LIMIT 20;

-- [TEST 2] VOD별 시청 통계 (목표: < 100ms)
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) AS views,
       AVG(completion_rate) AS avg_cr,
       AVG(satisfaction) AS avg_sat
FROM watch_history
WHERE vod_id_fk = (SELECT full_asset_id FROM vod LIMIT 1);

-- [TEST 3] 날짜 범위 집계 (목표: < 500ms)
EXPLAIN (ANALYZE, BUFFERS)
SELECT DATE(strt_dt) AS dt,
       COUNT(DISTINCT user_id_fk) AS dau,
       COUNT(*) AS views
FROM watch_history
WHERE strt_dt BETWEEN '2025-01-01' AND '2025-01-31'
GROUP BY DATE(strt_dt)
ORDER BY dt;

-- [TEST 4] 만족도 상위 VOD (목표: < 200ms)
EXPLAIN (ANALYZE, BUFFERS)
SELECT vod_id_fk,
       COUNT(*) AS views,
       AVG(satisfaction) AS avg_sat
FROM watch_history
WHERE satisfaction > 0.6
GROUP BY vod_id_fk
ORDER BY avg_sat DESC
LIMIT 50;
```

### 3.3 EXPLAIN 결과 해석 기준

| 실행 계획 | 판단 |
|---------|------|
| `Index Scan` | 정상 |
| `Index Only Scan` | 최적 (커버링 인덱스) |
| `Seq Scan` on watch_history | 문제 → 인덱스 누락 |
| `Nested Loop` (소규모) | 정상 |
| `Hash Join` (대규모) | 정상 |
| `Merge Join` | 정상 |

---

## 4. 정규화 검증

### 4.1 1NF 검증
- **기준**: 모든 컬럼이 원자값 (분리 불가능한 단일 값)
- **확인 항목**:
  - `cast_lead`, `cast_guest`: JSON 형식이나 단일 TEXT 컬럼으로 저장 → 1NF 허용
  - `svod_scrb_cnt_grp`: '0건' 형식 단일 문자열 → 1NF 준수
  - 배열/리스트 타입 사용 없음 확인

### 4.2 2NF 검증 (복합 PK 없으므로 자동 충족)
```sql
-- WATCH_HISTORY: 복합 PK 없음 확인
SELECT contype, conkey
FROM pg_constraint
WHERE conrelid = 'watch_history'::regclass
  AND contype = 'p';
-- 결과: 단일 컬럼(watch_history_id)
```

### 4.3 3NF 검증

**확인 대상: 이행 종속 가능성**

| 테이블 | 의심 케이스 | 결론 |
|------|---------|------|
| VOD | `series_nm → episode_number` | 현재 episode_number 없음 → 문제 없음 |
| VOD | `ct_cl → genre` | genre는 vod 자체 속성 → 허용 |
| WATCH_HISTORY | `completion_rate` = use_tms/disp_rtm_sec | 파생 컬럼이나 성능을 위해 저장 (설계 문서에 명시) |
| USERS | 모든 속성이 sha2_hash에 직접 종속 | 3NF 준수 |

---

## 5. 샘플 데이터 검증 쿼리

### 5.1 사용자 샘플 확인

```sql
-- 설계요구사항.md 샘플과 일치 확인
SELECT sha2_hash, age_grp10, inhome_rate, svod_scrb_cnt_grp,
       paid_chnl_cnt_grp, ch_hh_avg_month1, kids_use_pv_month1, nfx_use_yn
FROM users
WHERE sha2_hash LIKE '0000f35144%'
LIMIT 1;
-- 기대: 60대, 50.0, 0건, 0건, 14.1, 0.0, FALSE
```

### 5.2 VOD 샘플 확인

```sql
SELECT full_asset_id, asset_nm, ct_cl, disp_rtm_sec, genre
FROM vod
WHERE full_asset_id = 'cjc|M4996864LFOL10619201';
-- 기대: '완전한 사육: 욕망의 시작', '영화', 4860, '드라마'
```

### 5.3 시청이력 샘플 확인

```sql
SELECT user_id_fk, vod_id_fk, strt_dt, use_tms, completion_rate, satisfaction
FROM watch_history
WHERE user_id_fk = '0000f3514448d06cddfb916d39bcee86560093ee1d3ea475c8c33b3dac8a18e4'
ORDER BY strt_dt
LIMIT 5;
```

---

## 6. 회귀 테스트 (스키마 변경 시)

스키마 변경이 발생하면 아래를 재실행:

```bash
# 전체 검증 스크립트 실행
psql -d vod_recommendation -f schema/validation_queries.sql

# 결과 출력 예시:
# row_counts: PASS (users=242702, vod=166159, wh=3992530)
# fk_integrity: PASS (orphan_users=0, orphan_vods=0)
# null_constraints: PASS
# satisfaction_dist: PASS (avg=0.443, median=0.354)
# performance_test1: PASS (100ms)
# performance_test2: PASS (80ms)
```

---

## 7. 테스트 실패 시 조치

| 실패 항목 | 조치 |
|---------|------|
| 행 수 불일치 | 마이그레이션 로그 확인, 중복/스킵 행 재검토 |
| FK 위반 건 발생 | 해당 user_id/vod_id 원본 데이터 확인 |
| Seq Scan 발생 | 해당 쿼리 인덱스 추가 또는 ANALYZE 재실행 |
| satisfaction 분포 불일치 | 마이그레이션 타입 변환 로직 재확인 |
| 성능 목표 미달 | 03_PERFORMANCE_PLAN.md 참고하여 인덱스 튜닝 |
