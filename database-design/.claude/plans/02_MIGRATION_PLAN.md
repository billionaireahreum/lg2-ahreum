# Plan 02 - 데이터 마이그레이션 계획

**목표**: CSV 파일 → PostgreSQL 데이터베이스 마이그레이션
**우선순위**: 필수 (Phase 2)
**선행 조건**: `schema/create_tables.sql` 실행 완료

---

## 1. 마이그레이션 대상 파일

| CSV 파일 | 대상 테이블 | 예상 행 수 |
|---------|-----------|---------|
| `data/prepared_data/user_table.csv` | `users` | ~242,702 |
| `data/prepared_data/vod_table.csv` | `vod` | ~166,159 |
| `data/prepared_data/watch_history_table.csv` | `watch_history` | ~3,992,530 |

---

## 2. 컬럼 매핑

### USER (CSV → PostgreSQL)
| CSV 컬럼 | DB 컬럼 | 변환 처리 |
|---------|--------|---------|
| `sha2_hash` | `sha2_hash` | 그대로 |
| `AGE_GRP10` | `age_grp10` | 소문자화 |
| `INHOME_RATE` | `inhome_rate` | FLOAT → SMALLINT (ROUND) |
| `SVOD_SCRB_CNT_GRP` | `svod_scrb_cnt_grp` | 그대로 ('0건', '1건') |
| `PAID_CHNL_CNT_GRP` | `paid_chnl_cnt_grp` | 그대로 |
| `CH_HH_AVG_MONTH1` | `ch_hh_avg_month1` | FLOAT → NUMERIC(6,2) |
| `KIDS_USE_PV_MONTH1` | `kids_use_pv_month1` | FLOAT → NUMERIC(8,1) |
| `NFX_USE_YN` | `nfx_use_yn` | 'Y' → TRUE, 'N' → FALSE |

### VOD (CSV → PostgreSQL)
| CSV 컬럼 | DB 컬럼 | 변환 처리 |
|---------|--------|---------|
| `full_asset_id` | `full_asset_id` | 그대로 |
| `asset_nm` | `asset_nm` | 그대로 |
| `CT_CL` | `ct_cl` | 소문자화 |
| `disp_rtm` | `disp_rtm` | 그대로 ('HH:MM' 형식) |
| `disp_rtm_sec` | `disp_rtm_sec` | FLOAT → INTEGER (ROUND) |
| `genre` | `genre` | 그대로 |
| `director` | `director` | NULL('-') 처리 |
| `asset_prod` | `asset_prod` | 그대로 |
| `smry` | `smry` | NULL 처리 |
| `provider` | `provider` | 그대로 |
| `genre_detail` | `genre_detail` | 그대로 |
| `series_nm` | `series_nm` | 그대로 |

### WATCH_HISTORY (CSV → PostgreSQL)
| CSV 컬럼 | DB 컬럼 | 변환 처리 |
|---------|--------|---------|
| `sha2_hash` | `user_id_fk` | 그대로 |
| `full_asset_id` | `vod_id_fk` | 그대로 |
| `strt_dt` | `strt_dt` | 문자열 → TIMESTAMP |
| `use_tms` | `use_tms` | FLOAT → INTEGER |
| `completion_rate` | `completion_rate` | FLOAT → NUMERIC(8,4) |
| `satisfaction` | `satisfaction` | FLOAT → NUMERIC(8,4) |

---

## 3. 마이그레이션 스크립트 구조 (`migration/migrate.py`)

```python
# 전체 구조
migrate.py
├── class DatabaseConfig          # DB 연결 설정
├── class DataValidator           # 데이터 검증
├── class DataTransformer         # 컬럼 변환
├── class MigrationRunner         # 마이그레이션 실행
└── main()                        # 실행 진입점
```

### 주요 처리 로직

#### 1) NULL 처리 규칙
```python
# director: '-' 또는 빈 문자열 → None
director = None if raw_value in ['-', '', 'nan', 'NaN'] else raw_value

# nfx_use_yn: 'Y' → True, 'N' → False
nfx_use_yn = raw_value.strip().upper() == 'Y'
```

#### 2) 타입 변환
```python
# inhome_rate: float → int (10 단위)
inhome_rate = int(round(float(raw_value)))

# disp_rtm_sec: float → int
disp_rtm_sec = int(round(float(raw_value)))

# strt_dt: 문자열 → datetime
strt_dt = pd.to_datetime(raw_value)
```

#### 3) 중복 처리 (WATCH_HISTORY)
원본 데이터에서 동일 (sha2_hash, full_asset_id, strt_dt)에 여러 행이 존재할 수 있음.
→ 마이그레이션 전 분석 필요:
```python
# 중복 행 확인
duplicates = df.duplicated(subset=['sha2_hash', 'full_asset_id', 'strt_dt'], keep=False)
print(f"중복 행 수: {duplicates.sum()}")

# 처리 전략 선택:
# A) keep='last' - 마지막 레코드 유지 (가장 최신 시청 데이터)
# B) keep='first' - 첫 번째 레코드 유지
# C) 집계 - use_tms 합산, completion_rate/satisfaction 최대값
```

---

## 4. 마이그레이션 순서

```
1. PostgreSQL 연결 확인
2. 스키마 생성 확인 (테이블 존재 여부)
3. USER 마이그레이션
   - user_table.csv 로드
   - 컬럼 변환
   - COPY 또는 batch INSERT
   - 검증 (COUNT 확인)
4. VOD 마이그레이션
   - vod_table.csv 로드
   - 컬럼 변환 + NULL 처리
   - COPY 또는 batch INSERT
   - 검증 (COUNT 확인)
5. WATCH_HISTORY 마이그레이션
   - watch_history_table.csv 로드 (대용량)
   - 중복 처리
   - 컬럼 변환
   - FK 참조 무결성 확인
   - 청크 단위 INSERT (100,000행 단위)
   - 검증 (COUNT 확인)
6. 인덱스 생성 (마이그레이션 후 생성이 더 빠름)
7. 최종 데이터 정합성 검증
```

---

## 5. 성능 전략

### COPY 명령 활용 (bulk insert)
```python
# psycopg2 copy_from 사용 (INSERT보다 10~100배 빠름)
with conn.cursor() as cur:
    with open('user_table.csv') as f:
        cur.copy_expert(
            "COPY users FROM STDIN WITH CSV HEADER NULL 'nan'",
            f
        )
```

### 인덱스 생성 시점
- 대용량 INSERT 중에는 인덱스 업데이트 오버헤드 발생
- 마이그레이션 **완료 후** 인덱스 생성
- FK 제약조건도 마이그레이션 후 추가 (또는 DEFERRED 설정)

### 청크 단위 처리
```python
# WATCH_HISTORY: 100,000행씩 처리
CHUNK_SIZE = 100_000
for chunk in pd.read_csv('watch_history_table.csv', chunksize=CHUNK_SIZE):
    process_and_insert(chunk)
    print(f"Processed {len(chunk)} rows")
```

---

## 6. 데이터 검증 쿼리 (마이그레이션 후)

```sql
-- 테이블별 행 수 확인
SELECT 'users' AS tbl, COUNT(*) FROM users
UNION ALL
SELECT 'vod', COUNT(*) FROM vod
UNION ALL
SELECT 'watch_history', COUNT(*) FROM watch_history;

-- FK 참조 무결성 확인
SELECT COUNT(*) FROM watch_history wh
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.sha2_hash = wh.user_id_fk);

SELECT COUNT(*) FROM watch_history wh
WHERE NOT EXISTS (SELECT 1 FROM vod v WHERE v.full_asset_id = wh.vod_id_fk);

-- NULL 비율 확인
SELECT
    COUNT(*) FILTER (WHERE director IS NULL) AS director_null,
    COUNT(*) FILTER (WHERE smry IS NULL) AS smry_null,
    COUNT(*) AS total
FROM vod;

-- satisfaction 분포 확인 (설계요구사항.md 기준값과 비교)
SELECT
    COUNT(*) FILTER (WHERE satisfaction = 0) AS zero_sat,
    COUNT(*) FILTER (WHERE satisfaction BETWEEN 0.01 AND 0.2) AS low_sat,
    COUNT(*) FILTER (WHERE satisfaction BETWEEN 0.2 AND 0.6) AS mid_sat,
    COUNT(*) FILTER (WHERE satisfaction > 0.6) AS high_sat,
    AVG(satisfaction) AS avg_sat,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY satisfaction) AS median_sat
FROM watch_history;
```

### 기대 검증 결과 (설계요구사항.md 기준)
| 항목 | 기대값 |
|------|--------|
| users 행 수 | ~242,702 |
| vod 행 수 | ~166,159 |
| watch_history 행 수 | ~3,992,530 |
| FK 무결성 위반 | 0건 |
| avg satisfaction | ~0.443 |
| median satisfaction | ~0.354 |

---

## 7. 에러 처리 전략

| 에러 유형 | 처리 방법 |
|---------|---------|
| FK 위반 (미등록 user) | 로그 기록 후 해당 행 스킵 |
| FK 위반 (미등록 vod) | 로그 기록 후 해당 행 스킵 |
| 중복 키 (UNIQUE 위반) | ON CONFLICT DO NOTHING |
| NULL 불허 컬럼 NULL | 에러 중단 + 로그 |
| 타입 변환 실패 | 로그 기록 후 해당 행 스킵 |

---

## 8. 롤백 전략

```sql
-- 마이그레이션 실패 시 롤백
BEGIN;
-- 마이그레이션 실행
COMMIT;  -- 또는 ROLLBACK;

-- 테이블 초기화 (재실행 시)
TRUNCATE TABLE watch_history, vod, users RESTART IDENTITY CASCADE;
```

---

## 9. 환경 설정

```python
# config.py
DATABASE_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "vod_recommendation",
    "user": "postgres",
    "password": "...",
}

DATA_DIR = "database-design/data/prepared_data/"
CHUNK_SIZE = 100_000
LOG_LEVEL = "INFO"
```

---

## 10. 예상 소요 시간

| 단계 | 예상 시간 |
|------|---------|
| USER 마이그레이션 (242,702행) | ~30초 |
| VOD 마이그레이션 (166,159행) | ~20초 |
| WATCH_HISTORY 마이그레이션 (3,992,530행) | ~5~10분 |
| 인덱스 생성 | ~2~5분 |
| 검증 쿼리 실행 | ~1분 |
| **총 예상 시간** | **~15분** |
