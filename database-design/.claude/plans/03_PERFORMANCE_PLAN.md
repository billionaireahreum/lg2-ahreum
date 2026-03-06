# Plan 03 - 성능 최적화 계획

**목표**: 10,000+ QPS 처리, 주요 쿼리 응답시간 목표 달성
**우선순위**: 필수 (Phase 3)
**선행 조건**: 마이그레이션 완료

---

## 1. 성능 목표

| 쿼리 패턴 | 목표 응답시간 | 데이터 규모 |
|---------|------------|---------|
| 사용자별 시청이력 조회 | < 100ms | 평균 16.45행/사용자 |
| VOD별 시청 통계 | < 100ms | 평균 24.03행/VOD |
| 날짜 범위 조회 (1개월) | < 500ms | ~3,992,530행 |
| 만족도 상위 VOD 조회 | < 200ms | 전체 테이블 |
| 전체 처리량 | 10,000 QPS | - |

---

## 2. 인덱스 전략

### 2.1 WATCH_HISTORY 인덱스 (핵심)

```sql
-- [HIGH] 사용자별 조회 - 가장 빈번한 패턴
CREATE INDEX idx_wh_user_id
    ON watch_history(user_id_fk);

-- [HIGH] VOD별 조회
CREATE INDEX idx_wh_vod_id
    ON watch_history(vod_id_fk);

-- [HIGH] 날짜 범위 조회
CREATE INDEX idx_wh_strt_dt
    ON watch_history(strt_dt DESC);

-- [HIGH] 사용자별 시간순 조회 (커버링 인덱스 효과)
CREATE INDEX idx_wh_user_strt
    ON watch_history(user_id_fk, strt_dt DESC);

-- [MEDIUM] 만족도 순위 조회
CREATE INDEX idx_wh_satisfaction
    ON watch_history(satisfaction DESC)
    WHERE satisfaction > 0;  -- 부분 인덱스: 0점 제외

-- [MEDIUM] VOD별 만족도 통계 집계
CREATE INDEX idx_wh_vod_sat
    ON watch_history(vod_id_fk, satisfaction);
```

### 2.2 VOD 인덱스

```sql
-- [HIGH] 콘텐츠 유형 필터
CREATE INDEX idx_vod_ct_cl ON vod(ct_cl);

-- [MEDIUM] 장르 필터
CREATE INDEX idx_vod_genre ON vod(genre);

-- [LOW] RAG 배치 처리용 부분 인덱스
CREATE INDEX idx_vod_rag_pending
    ON vod(created_at)
    WHERE rag_processed = FALSE;

-- [MEDIUM] 전문 검색 (GIN)
CREATE INDEX idx_vod_fts
    ON vod
    USING GIN(to_tsvector('simple',
        COALESCE(asset_nm, '') || ' ' ||
        COALESCE(smry, '') || ' ' ||
        COALESCE(genre, '')
    ));
```

### 2.3 USERS 인덱스

```sql
-- [MEDIUM] 연령대 세그멘테이션
CREATE INDEX idx_users_age ON users(age_grp10);

-- [LOW] NFX 사용자 필터 (부분 인덱스)
CREATE INDEX idx_users_nfx
    ON users(sha2_hash)
    WHERE nfx_use_yn = TRUE;
```

---

## 3. 쿼리 패턴별 실행 계획 분석

### 3.1 사용자별 시청이력 조회

```sql
-- 목표: < 100ms
EXPLAIN ANALYZE
SELECT
    wh.strt_dt,
    wh.use_tms,
    wh.completion_rate,
    wh.satisfaction,
    v.asset_nm,
    v.genre
FROM watch_history wh
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE wh.user_id_fk = 'abc123...'
ORDER BY wh.strt_dt DESC
LIMIT 20;

-- 기대 실행 계획:
-- Index Scan using idx_wh_user_strt on watch_history
-- → Nested Loop Join with vod (PK lookup)
```

### 3.2 VOD별 시청 통계

```sql
-- 목표: < 100ms
EXPLAIN ANALYZE
SELECT
    COUNT(*) AS view_count,
    AVG(completion_rate) AS avg_completion,
    AVG(satisfaction) AS avg_satisfaction,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY satisfaction) AS median_sat
FROM watch_history
WHERE vod_id_fk = 'cjc|M4996864LFOL10619201';

-- 기대 실행 계획:
-- Index Scan using idx_wh_vod_sat on watch_history
```

### 3.3 날짜 범위 + 집계 쿼리

```sql
-- 목표: < 500ms
EXPLAIN ANALYZE
SELECT
    DATE(strt_dt) AS watch_date,
    COUNT(DISTINCT user_id_fk) AS dau,
    COUNT(*) AS total_views,
    AVG(satisfaction) AS avg_sat
FROM watch_history
WHERE strt_dt BETWEEN '2025-01-01' AND '2025-01-31'
GROUP BY DATE(strt_dt)
ORDER BY watch_date;

-- 기대 실행 계획:
-- Index Scan using idx_wh_strt_dt
-- → HashAggregate
```

### 3.4 만족도 상위 VOD 순위

```sql
-- 목표: < 200ms
EXPLAIN ANALYZE
SELECT
    v.full_asset_id,
    v.asset_nm,
    v.genre,
    COUNT(wh.watch_history_id) AS view_count,
    AVG(wh.satisfaction) AS avg_sat
FROM vod v
JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
WHERE wh.satisfaction > 0.6
GROUP BY v.full_asset_id, v.asset_nm, v.genre
HAVING COUNT(*) >= 10
ORDER BY avg_sat DESC
LIMIT 50;
```

---

## 4. 파티셔닝 전략

### 4.1 WATCH_HISTORY 범위 파티셔닝 (권장)

현재 데이터 규모(~400만 행)에서는 파티셔닝이 필수적이지 않으나, 향후 데이터 증가를 위해 설계.

```sql
-- 파티션 테이블로 재생성
CREATE TABLE watch_history (
    watch_history_id BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id_fk      VARCHAR(64) NOT NULL,
    vod_id_fk       VARCHAR(64) NOT NULL,
    strt_dt         TIMESTAMP   NOT NULL,
    -- ... 나머지 컬럼
    PRIMARY KEY (watch_history_id, strt_dt)  -- 파티션 키 포함 필수
) PARTITION BY RANGE (strt_dt);

-- 파티션 생성 (월별)
CREATE TABLE watch_history_2025_01
    PARTITION OF watch_history
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE watch_history_2025_02
    PARTITION OF watch_history
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

-- 인덱스는 각 파티션에 자동 적용
```

### 4.2 파티셔닝 적용 기준

| 조건 | 파티셔닝 적용 여부 |
|------|----------------|
| 데이터 < 1,000만 행 | 선택적 (성능 이득 적음) |
| 데이터 > 1,000만 행 | 강력 권장 |
| 날짜 범위 쿼리 비율 > 30% | 권장 |
| 오래된 데이터 아카이브 필요 | 권장 |

**현재 판단**: Phase 1에서는 파티셔닝 없이 진행, 데이터 증가 시 Phase 3에서 적용.

---

## 5. 연결 풀링 및 캐싱 전략

### 5.1 PostgreSQL 설정 튜닝 (postgresql.conf)

```ini
# 메모리 설정 (서버 RAM 16GB 기준 예시)
shared_buffers = 4GB              # RAM의 25%
effective_cache_size = 12GB       # RAM의 75%
work_mem = 256MB                  # 정렬/해시 연산용
maintenance_work_mem = 1GB        # VACUUM, CREATE INDEX용

# 연결 설정
max_connections = 200             # PgBouncer 사용 시 줄여도 됨

# WAL 설정 (쓰기 성능)
wal_buffers = 64MB
checkpoint_completion_target = 0.9

# 통계 수집
track_io_timing = on
log_min_duration_statement = 100  # 100ms 이상 쿼리 로깅
```

### 5.2 PgBouncer 연결 풀링 (10,000 QPS 목표)

```ini
# pgbouncer.ini
pool_mode = transaction           # 트랜잭션 풀링
max_client_conn = 10000
default_pool_size = 100
min_pool_size = 20
```

### 5.3 캐싱 계층 (향후 Redis)

```
요청 → Redis L1 캐시 (TTL 1시간)
      ↓ 미스
      → PostgreSQL
      ↓
      → Redis에 캐시 저장
```

캐시 대상:
- 사용자 추천 결과 (user_id → Top-100 VOD)
- 인기 VOD 통계 (VOD별 avg_satisfaction)
- 연령대별 인기 VOD

---

## 6. VACUUM 및 유지보수 전략

```sql
-- autovacuum 설정 (watch_history는 INSERT가 많으므로 조정)
ALTER TABLE watch_history SET (
    autovacuum_vacuum_scale_factor = 0.01,   -- 1% 변경 시 VACUUM
    autovacuum_analyze_scale_factor = 0.005  -- 0.5% 변경 시 ANALYZE
);

-- 통계 정보 갱신 (마이그레이션 후 필수)
ANALYZE users;
ANALYZE vod;
ANALYZE watch_history;
```

---

## 7. 성능 테스트 파일 (`schema/performance_test.sql`)

작성할 파일 구조:
```sql
-- ========================================
-- 성능 테스트 쿼리 모음
-- 실행: psql -f performance_test.sql
-- ========================================

-- [TEST 1] 사용자별 시청이력 조회
\timing on
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT ... WHERE user_id_fk = '...';

-- [TEST 2] VOD별 통계
EXPLAIN (ANALYZE, BUFFERS)
SELECT ... WHERE vod_id_fk = '...';

-- [TEST 3] 날짜 범위 집계
EXPLAIN (ANALYZE, BUFFERS)
SELECT ... WHERE strt_dt BETWEEN ... AND ...;

-- [TEST 4] 만족도 순위
EXPLAIN (ANALYZE, BUFFERS)
SELECT ... ORDER BY satisfaction DESC LIMIT 50;
```

---

## 8. 인덱스 생성 순서 (마이그레이션 후)

```
1. 마이그레이션 완료 확인
2. ANALYZE (통계 수집)
3. PRIMARY KEY 인덱스 (자동 생성)
4. WATCH_HISTORY HIGH 우선순위 인덱스 (idx_wh_user_id, idx_wh_vod_id, idx_wh_strt_dt)
5. WATCH_HISTORY 복합 인덱스 (idx_wh_user_strt)
6. VOD 인덱스
7. USERS 인덱스
8. GIN 인덱스 (전문 검색, 가장 느림)
9. 성능 테스트 실행
10. EXPLAIN ANALYZE 결과 확인
```

---

## 9. 성능 모니터링 쿼리

```sql
-- 인덱스 사용률 확인
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan AS scans,
    idx_tup_read AS tuples_read
FROM pg_stat_user_indexes
WHERE tablename IN ('users', 'vod', 'watch_history')
ORDER BY idx_scan DESC;

-- 느린 쿼리 확인 (pg_stat_statements 활성화 필요)
SELECT
    query,
    calls,
    mean_exec_time,
    total_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC
LIMIT 20;

-- 테이블 크기 확인
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(tablename::regclass)) AS total_size,
    pg_size_pretty(pg_relation_size(tablename::regclass)) AS table_size,
    pg_size_pretty(pg_indexes_size(tablename::regclass)) AS index_size
FROM (VALUES ('users'), ('vod'), ('watch_history')) AS t(tablename);
```
