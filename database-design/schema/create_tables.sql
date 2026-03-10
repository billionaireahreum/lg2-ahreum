-- ============================================================
-- VOD 추천 시스템 - PostgreSQL 테이블 DDL
-- 대상 DB : vod_recommendation
-- 작성일  : 2026-03-06
-- 참고    : database-design/.claude/plans/01_DDL_PLAN.md
--
-- 실행 순서: users → vod → watch_history (FK 의존성)
-- ============================================================


-- ============================================================
-- 0. 사전 준비
-- ============================================================

-- updated_at 자동 갱신 트리거 함수 (공통)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 1. USERS 테이블
--    원본: user_table (스테이징)
--    행 수: ~242,702
--    PK   : sha2_hash (SHA-2 해시, 복호화 불가 → PII 보호)
-- ============================================================

CREATE TABLE users (

    -- 식별자
    sha2_hash           VARCHAR(64)     NOT NULL,

    -- 인구통계
    age_grp10           VARCHAR(16),                        -- '10대', '20대', ..., '90대이상'
    gender              VARCHAR(8),                         -- 원본 없음, RAG/추후 수집

    -- 행동 패턴
    inhome_rate         SMALLINT,                           -- 집돌이 지수 0~100 (10단위)
    ch_hh_avg_month1    NUMERIC(6,2),                       -- 월평균 TV 시청 시간(시간)

    -- 구독 현황 (원본 '0건','1건' 문자열 그대로 유지)
    svod_scrb_cnt_grp   VARCHAR(16),                        -- SVOD 구독 건수 그룹
    paid_chnl_cnt_grp   VARCHAR(16),                        -- 유료 채널 건수 그룹

    -- 특화 콘텐츠
    kids_use_pv_month1  NUMERIC(8,1),                       -- 키즈 콘텐츠 월 시청 분

    -- 외부 서비스
    nfx_use_yn          BOOLEAN         NOT NULL DEFAULT FALSE,  -- Netflix 사용 여부

    -- 메타데이터
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_active_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_users PRIMARY KEY (sha2_hash)
);

COMMENT ON TABLE  users                    IS '사용자 정보 테이블 - SHA-2 해시 익명화된 사용자 데이터';
COMMENT ON COLUMN users.sha2_hash          IS 'SHA-2 해시 사용자 ID (64자, 단방향 암호화 → 복호화 불가)';
COMMENT ON COLUMN users.age_grp10          IS '연령대 그룹: 10대/20대/.../90대이상';
COMMENT ON COLUMN users.inhome_rate        IS '집돌이 지수 (0~100, 10단위 반올림)';
COMMENT ON COLUMN users.ch_hh_avg_month1   IS '월평균 TV 시청 시간 (시간 단위)';
COMMENT ON COLUMN users.svod_scrb_cnt_grp  IS 'SVOD 구독 건수 그룹 (원본 문자열: 0건/1건/2건이상)';
COMMENT ON COLUMN users.paid_chnl_cnt_grp  IS '유료 채널 건수 그룹 (원본 문자열: 0건/1건/2건이상)';
COMMENT ON COLUMN users.kids_use_pv_month1 IS '키즈 콘텐츠 월 시청 분 (0.0이면 미시청)';
COMMENT ON COLUMN users.nfx_use_yn         IS 'Netflix 사용 여부 (원본 Y→TRUE, N→FALSE)';


-- ============================================================
-- 2. VOD 테이블
--    원본: vod_table (스테이징)
--    행 수: ~166,159
--    PK   : full_asset_id (예: 'cjc|M4996864LFOL10619201')
--    결측치: director(313건), smry(28건) → NULL 허용, RAG 처리 예정
-- ============================================================

CREATE TABLE vod (

    -- 식별자
    full_asset_id       VARCHAR(64)     NOT NULL,           -- 예: 'cjc|M4996864LFOL10619201'

    -- 기본 메타데이터
    asset_nm            VARCHAR(255)    NOT NULL,           -- 콘텐츠명
    ct_cl               VARCHAR(32)     NOT NULL,           -- 대분류: 영화/드라마/라이프/...
    genre               VARCHAR(64),                        -- 장르: 드라마/코미디/SF/...
    genre_detail        VARCHAR(255),                       -- 상세 장르
    provider            VARCHAR(128),                       -- 제공사
    asset_prod          VARCHAR(64),                        -- 결제 유형: FOD(무료)/...
    series_nm           VARCHAR(255),                       -- 시리즈명 (단편이면 NULL)

    -- 기술 사양
    disp_rtm            VARCHAR(16),                        -- 표시용 재생시간 'HH:MM' 형식
    disp_rtm_sec        INTEGER         NOT NULL,           -- 재생시간(초) - 만족도 계산 기준

    -- 제작진 (결측치 허용 - RAG 파이프라인 처리 예정)
    director            VARCHAR(255),                       -- 감독명 (NULL 313건)
    cast_lead           TEXT,                               -- 주연 배우 (RAG 추가 예정)
    cast_guest          TEXT,                               -- 조연 배우 (RAG 추가 예정)

    -- 설명 (결측치 허용 - RAG 파이프라인 처리 예정)
    smry                TEXT,                               -- 줄거리 (NULL 28건)
    keywords            TEXT,                               -- 키워드 (RAG 추가 예정)

    -- 분류 정보 (RAG 처리 예정)
    rating              VARCHAR(16),                        -- 시청등급: 전체이용가/12세이상/...
    release_date        DATE,                               -- 개봉/방영일

    -- RAG 추적 컬럼
    rag_processed       BOOLEAN         NOT NULL DEFAULT FALSE,
    rag_source          VARCHAR(64),                        -- 'IMDB', 'Wiki', 'KMRB', ...
    rag_processed_at    TIMESTAMP,

    -- 메타데이터
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_vod PRIMARY KEY (full_asset_id)
);

COMMENT ON TABLE  vod                  IS 'VOD 콘텐츠 메타데이터 테이블 (~166,159개)';
COMMENT ON COLUMN vod.full_asset_id    IS 'VOD 고유 식별자 (예: cjc|M4996864LFOL10619201)';
COMMENT ON COLUMN vod.ct_cl            IS '콘텐츠 대분류 (영화/드라마/예능/라이프/...)';
COMMENT ON COLUMN vod.disp_rtm         IS '표시용 재생시간 (HH:MM 형식, UI 표시용)';
COMMENT ON COLUMN vod.disp_rtm_sec     IS '재생시간 초 단위 (satisfaction 계산 기준값)';
COMMENT ON COLUMN vod.director         IS '감독명 - NULL 허용 (RAG 파이프라인으로 채울 예정)';
COMMENT ON COLUMN vod.smry             IS '줄거리 - NULL 허용 (RAG 파이프라인으로 채울 예정)';
COMMENT ON COLUMN vod.rag_processed    IS 'RAG 파이프라인 처리 완료 여부';
COMMENT ON COLUMN vod.rag_source       IS 'RAG 데이터 출처 (IMDB/Wikipedia/KMRB 등)';
COMMENT ON COLUMN vod.rag_processed_at IS 'RAG 처리 완료 시각';

-- updated_at 자동 갱신 트리거
CREATE TRIGGER trg_vod_updated_at
    BEFORE UPDATE ON vod
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- 3. WATCH_HISTORY 테이블
--    원본: watch_history_table (스테이징)
--    행 수: ~3,992,530
--    PK   : watch_history_id (자동 생성 BIGINT)
--    만족도: 베이지안 스코어 (v*R + m*C)/(v+m), CSV에서 직접 로드
-- ============================================================

CREATE TABLE watch_history (

    -- 식별자 (자동 생성)
    watch_history_id    BIGINT          GENERATED ALWAYS AS IDENTITY,

    -- 외래키
    user_id_fk          VARCHAR(64)     NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL,

    -- 시간 정보
    strt_dt             TIMESTAMP       NOT NULL,           -- 시청 시작 시각
    end_dt              TIMESTAMP,                          -- 시청 종료 시각 (원본 없음)

    -- 재생 통계
    use_tms             INTEGER         NOT NULL,           -- 실제 시청 시간(초)
    completion_rate     NUMERIC(8,4)    NOT NULL,           -- 시청 완주율 (0.0~1.0)

    -- 만족도 (베이지안 스코어, CSV에서 직접 로드)
    -- 공식: (v * R + m * C) / (v + m)
    --   v=VOD별 시청건수, R=시청비율, C=전체평균(~0.47), m=5.0
    --   60초 이하 시청 → 0.0
    satisfaction        NUMERIC(8,4)    NOT NULL DEFAULT 0.0,

    -- 세션 정보 (원본 없음, 향후 수집 예정)
    device_type         VARCHAR(32),                        -- 'PC', 'MOBILE', 'TV'
    status              VARCHAR(16),                        -- 'COMPLETED', 'ABANDONED', 'PAUSED'
    is_rewatch          BOOLEAN         NOT NULL DEFAULT FALSE,

    CONSTRAINT pk_watch_history PRIMARY KEY (watch_history_id),
    CONSTRAINT fk_wh_user FOREIGN KEY (user_id_fk)
        REFERENCES users(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT fk_wh_vod  FOREIGN KEY (vod_id_fk)
        REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT uq_watch_session UNIQUE (user_id_fk, vod_id_fk, strt_dt)
);

COMMENT ON TABLE  watch_history                 IS '사용자 시청 이력 테이블 - 핵심 팩트 테이블 (~3,992,530건)';
COMMENT ON COLUMN watch_history.watch_history_id IS '시청 이력 고유 ID (자동 생성)';
COMMENT ON COLUMN watch_history.user_id_fk       IS 'users.sha2_hash 참조';
COMMENT ON COLUMN watch_history.vod_id_fk        IS 'vod.full_asset_id 참조';
COMMENT ON COLUMN watch_history.use_tms          IS '실제 시청 시간(초) - 60초 이하면 satisfaction=0';
COMMENT ON COLUMN watch_history.completion_rate  IS '시청 완주율 = use_tms / disp_rtm_sec (0.0~1.0)';
COMMENT ON COLUMN watch_history.satisfaction     IS '베이지안 만족도 스코어 (0.0~1.0): (v*R+m*C)/(v+m), m=5.0';
