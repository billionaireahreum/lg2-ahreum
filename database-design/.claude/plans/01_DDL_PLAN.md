# Plan 01 - DDL 스크립트 작성 계획

**목표**: PostgreSQL 전용 DDL 스크립트 작성 (`schema/create_tables.sql`, `schema/create_indexes.sql`)
**우선순위**: 필수 (Phase 1)
**선행 조건**: 없음

---

## 1. 작성할 파일

| 파일 | 내용 |
|------|------|
| `schema/create_tables.sql` | USER, VOD, WATCH_HISTORY 테이블 CREATE 문 |
| `schema/create_indexes.sql` | 모든 인덱스 CREATE 문 |
| `schema/DESIGN.md` | 각 설계 결정의 이유 설명 |

---

## 2. USER 테이블 설계

### 원본 컬럼 (CSV)
```
sha2_hash, AGE_GRP10, INHOME_RATE, SVOD_SCRB_CNT_GRP,
PAID_CHNL_CNT_GRP, CH_HH_AVG_MONTH1, KIDS_USE_PV_MONTH1, NFX_USE_YN
```

### PostgreSQL DDL 목표
```sql
CREATE TABLE users (
    -- 식별자 (원본 해시값, PK)
    sha2_hash       VARCHAR(64)     PRIMARY KEY,

    -- 인구통계
    age_grp10       VARCHAR(16),                    -- '10대', '20대', ..., '90대이상'
    gender          VARCHAR(8),                     -- 원본에 없음, NULL 허용

    -- 행동 패턴
    inhome_rate     SMALLINT,                       -- 0~100 (10단위 반올림)
    ch_hh_avg_month1 NUMERIC(6,2),                  -- 월평균 TV 시청 시간

    -- 구독 현황
    svod_scrb_cnt_grp VARCHAR(16),                  -- '0건', '1건', ... (원본 문자열 그대로)
    paid_chnl_cnt_grp VARCHAR(16),                  -- '0건', '1건', ...

    -- 특화 콘텐츠
    kids_use_pv_month1 NUMERIC(8,1),                -- 키즈 콘텐츠 월 시청 분

    -- 외부 서비스
    nfx_use_yn      BOOLEAN         NOT NULL DEFAULT FALSE,  -- 'Y'→TRUE, 'N'→FALSE

    -- 메타데이터
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_active_at  TIMESTAMP       NOT NULL DEFAULT NOW()
);
```

### 설계 결정 포인트
- **테이블명**: `users` (PostgreSQL 예약어 `user` 충돌 회피)
- **PK**: sha2_hash (64자 해시, 단방향 → 복호화 불가, PII 보호)
- **svod/paid 컬럼**: 원본이 '0건', '1건' 문자열이므로 VARCHAR 유지
  - 향후 숫자 변환 필요 시 마이그레이션에서 처리
- **nfx_use_yn**: 'Y'/'N' → BOOLEAN 변환 (마이그레이션 시)
- **gender**: 원본 데이터에 없으나 논리적 스키마에 정의됨 → NULL 허용으로 포함

---

## 3. VOD 테이블 설계

### 원본 컬럼 (CSV)
```
full_asset_id, asset_nm, CT_CL, disp_rtm, disp_rtm_sec,
genre, director, asset_prod, smry, provider, genre_detail, series_nm
```

### PostgreSQL DDL 목표
```sql
CREATE TABLE vod (
    -- 식별자
    full_asset_id   VARCHAR(64)     PRIMARY KEY,    -- 예: 'cjc|M4996864LFOL10619201'

    -- 기본 메타데이터
    asset_nm        VARCHAR(255)    NOT NULL,
    ct_cl           VARCHAR(32)     NOT NULL,        -- 대분류: '영화', '라이프', ...
    genre           VARCHAR(64),
    genre_detail    VARCHAR(255),
    provider        VARCHAR(128),
    asset_prod      VARCHAR(64),                    -- 결제 유형: 'FOD', ...
    series_nm       VARCHAR(255),

    -- 기술 사양
    disp_rtm        VARCHAR(16),                    -- 원본 표시시간 'HH:MM' 형식
    disp_rtm_sec    INTEGER         NOT NULL,        -- 초 단위 (계산 기준)

    -- 제작진 (결측치 허용 - RAG 처리 예정)
    director        VARCHAR(255),
    cast_lead       TEXT,
    cast_guest      TEXT,

    -- 설명 (결측치 허용 - RAG 처리 예정)
    smry            TEXT,
    keywords        TEXT,

    -- 분류 정보 (RAG 처리 예정)
    rating          VARCHAR(16),
    release_date    DATE,

    -- RAG 추적 컬럼
    rag_processed   BOOLEAN         NOT NULL DEFAULT FALSE,
    rag_source      VARCHAR(64),                    -- 'IMDB', 'Wiki', 'KMRB', ...
    rag_processed_at TIMESTAMP,

    -- 메타데이터
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);
```

### 설계 결정 포인트
- **disp_rtm vs disp_rtm_sec**: 원본에 두 컬럼 모두 존재 → 양쪽 저장
  - `disp_rtm`: '01:21' 형식 (표시용)
  - `disp_rtm_sec`: 4860.0 (계산용, NOT NULL)
- **director, smry**: NULL 허용 → RAG 파이프라인으로 채울 예정
- **rag_processed 컬럼 3개**: RAG 처리 상태 추적용
- **full_asset_id**: 'cjc|M...' 형식으로 64자 이내 → VARCHAR(64) 적합

---

## 4. WATCH_HISTORY 테이블 설계

### 원본 컬럼 (CSV)
```
sha2_hash, full_asset_id, strt_dt, use_tms, completion_rate, satisfaction
```

### PostgreSQL DDL 목표
```sql
CREATE TABLE watch_history (
    -- 식별자 (자동 생성)
    watch_history_id BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- 외래키
    user_id_fk      VARCHAR(64)     NOT NULL REFERENCES users(sha2_hash) ON DELETE CASCADE,
    vod_id_fk       VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,

    -- 시간 정보
    strt_dt         TIMESTAMP       NOT NULL,
    end_dt          TIMESTAMP,                      -- 종료 시간 (원본 없음, NULL 허용)

    -- 재생 통계
    use_tms         INTEGER         NOT NULL,        -- 시청 시간 (초)
    completion_rate NUMERIC(8,4)    NOT NULL,        -- 시청 비율 (0.0~1.0)

    -- 만족도 (베이지안 스코어, CSV에서 직접 로드)
    satisfaction    NUMERIC(8,4)    NOT NULL DEFAULT 0.0,

    -- 세션 정보 (원본 없음, 향후 수집)
    device_type     VARCHAR(32),
    status          VARCHAR(16),                    -- 'COMPLETED', 'ABANDONED'
    is_rewatch      BOOLEAN         NOT NULL DEFAULT FALSE,

    -- 유니크 제약 (동일 사용자, 동일 VOD, 동일 시작시간 중복 방지)
    CONSTRAINT uq_watch_session UNIQUE (user_id_fk, vod_id_fk, strt_dt)
);
```

### 설계 결정 포인트
- **PK**: `watch_history_id` (BIGINT GENERATED ALWAYS AS IDENTITY)
  - PostgreSQL에서 AUTO_INCREMENT 대체
  - BIGINT: 3,992,530건 + 향후 증가 대비
- **satisfaction**: CSV에 이미 계산된 값 존재 → 직접 로드 (트리거 불필요)
  - 베이지안 스코어: `(v * R + m * C) / (v + m)`
- **completion_rate**: NUMERIC(8,4) → 소수점 4자리 (예: 0.3344)
- **UNIQUE 제약**: `(user_id_fk, vod_id_fk, strt_dt)` → 동일 세션 중복 방지
  - 단, 원본 데이터에 동일 (hash, asset_id, strt_dt)로 여러 행 존재 가능 → 마이그레이션 시 확인 필요

---

## 5. 인덱스 전략 (`create_indexes.sql`)

### 필수 인덱스 (HIGH 우선순위)
```sql
-- 사용자별 시청이력 조회 (가장 빈번)
CREATE INDEX idx_wh_user_id ON watch_history(user_id_fk);

-- VOD별 시청 통계 조회
CREATE INDEX idx_wh_vod_id ON watch_history(vod_id_fk);

-- 날짜 범위 조회
CREATE INDEX idx_wh_strt_dt ON watch_history(strt_dt);

-- 만족도 상위 VOD 조회
CREATE INDEX idx_wh_satisfaction ON watch_history(satisfaction DESC);
```

### 복합 인덱스 (MEDIUM 우선순위)
```sql
-- 사용자별 시간순 조회 (커버링 인덱스)
CREATE INDEX idx_wh_user_strt ON watch_history(user_id_fk, strt_dt DESC);

-- VOD별 만족도 통계
CREATE INDEX idx_wh_vod_sat ON watch_history(vod_id_fk, satisfaction);
```

### VOD 테이블 인덱스
```sql
-- 콘텐츠 유형 필터
CREATE INDEX idx_vod_ct_cl ON vod(ct_cl);

-- 장르 필터
CREATE INDEX idx_vod_genre ON vod(genre);

-- RAG 처리 상태 (배치 처리용)
CREATE INDEX idx_vod_rag ON vod(rag_processed) WHERE rag_processed = FALSE;

-- 전문 검색 (GIN 인덱스)
CREATE INDEX idx_vod_search ON vod USING GIN(
    to_tsvector('korean', COALESCE(asset_nm, '') || ' ' || COALESCE(smry, ''))
);
```

### USER 테이블 인덱스
```sql
-- 연령대 세그멘테이션
CREATE INDEX idx_users_age ON users(age_grp10);

-- NFX 사용자 필터 (부분 인덱스)
CREATE INDEX idx_users_nfx ON users(nfx_use_yn) WHERE nfx_use_yn = TRUE;
```

---

## 6. 테이블 코멘트 추가

PostgreSQL 문법으로 COMMENT 작성:
```sql
COMMENT ON TABLE users IS '사용자 정보 테이블 - sha2 해시 익명화된 사용자 데이터';
COMMENT ON COLUMN users.sha2_hash IS 'SHA-2 해시 사용자 ID (64자, 복호화 불가)';
COMMENT ON COLUMN users.inhome_rate IS '집돌이 지수 (0~100, 10단위)';

COMMENT ON TABLE vod IS 'VOD 콘텐츠 메타데이터 테이블';
COMMENT ON COLUMN vod.disp_rtm_sec IS '영상 전체 길이 (초 단위, 만족도 계산 기준)';
COMMENT ON COLUMN vod.rag_processed IS 'RAG 파이프라인 처리 완료 여부';

COMMENT ON TABLE watch_history IS '사용자 시청 이력 테이블 (핵심 팩트 테이블)';
COMMENT ON COLUMN watch_history.satisfaction IS '베이지안 만족도 스코어 (0.0~1.0): (v*R + m*C)/(v+m)';
COMMENT ON COLUMN watch_history.completion_rate IS '시청 완주율 (use_tms / disp_rtm_sec, 0.0~1.0)';
```

---

## 7. 정규화 검증 체크리스트

### 제1정규형 (1NF)
- [ ] 모든 컬럼이 원자값 (배열/리스트 없음)
- [ ] `cast_lead`, `cast_guest`: TEXT(JSON 형식) → 1NF 준수 (단일 값으로 취급)

### 제2정규형 (2NF)
- [ ] WATCH_HISTORY: 복합 키 없음 (단일 PK) → 2NF 자동 충족
- [ ] 부분 함수 종속 없음 확인

### 제3정규형 (3NF)
- [ ] USER 테이블: 이행 종속 없음 (모든 속성이 sha2_hash에만 종속)
- [ ] VOD 테이블: series_nm → episode_number 이행 종속 검토
  - series_nm은 vod 자체 속성으로 허용
- [ ] WATCH_HISTORY: completion_rate = use_tms / disp_rtm_sec → 파생 컬럼
  - 성능을 위해 저장 결정 (설계 문서에 명시)

---

## 8. 작업 순서

1. `schema/create_tables.sql` 작성
   - USER → VOD → WATCH_HISTORY 순서 (FK 의존성)
2. `schema/create_indexes.sql` 작성
3. `schema/DESIGN.md` 작성 (각 결정 이유)
4. PostgreSQL에서 문법 검증 (`psql`로 실행 확인)

---

## 9. 주의사항

- `user`는 PostgreSQL 예약어 → 테이블명 `users` 사용
- `disp_rtm_sec`의 원본 타입이 FLOAT → INTEGER로 변환 (`ROUND()` 적용)
- `UNIQUE (user_id_fk, vod_id_fk, strt_dt)` 적용 전 원본 데이터 중복 여부 확인 필요
  - 동일 (hash, asset, strt_dt)에 여러 행 존재할 경우 UNIQUE 적용 불가 → 마이그레이션에서 집계 처리
- GIN 인덱스의 한국어 토크나이저: 기본 `simple` config 사용 (pg_bigm 또는 별도 설정 가능)
