-- ============================================================
-- VOD 추천 시스템 - 데이터 마이그레이션
-- 스테이징 테이블 → 정규화된 테이블
-- 작성일: 2026-03-06
-- 참고  : database-design/.claude/plans/02_MIGRATION_PLAN.md
--
-- 실행 순서:
--   1. schema/create_tables.sql  (테이블 생성)
--   2. migration/migrate.sql     (이 파일 - 데이터 이동)
--   3. schema/create_indexes.sql (인덱스 생성)
--
-- 실행 방법:
--   psql -d vod_recommendation -f migration/migrate.sql
-- ============================================================


-- ============================================================
-- 사전 확인: 스테이징 테이블 존재 여부
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'user_table') THEN
        RAISE EXCEPTION '스테이징 테이블 user_table 이 없습니다.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'vod_table') THEN
        RAISE EXCEPTION '스테이징 테이블 vod_table 이 없습니다.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'watch_history_table') THEN
        RAISE EXCEPTION '스테이징 테이블 watch_history_table 이 없습니다.';
    END IF;
    RAISE NOTICE '스테이징 테이블 확인 완료.';
END $$;


-- ============================================================
-- STEP 1. users 마이그레이션
--   변환:
--     AGE_GRP10          → age_grp10        (컬럼명 소문자)
--     INHOME_RATE (text) → inhome_rate       (SMALLINT)
--     CH_HH_AVG_MONTH1   → ch_hh_avg_month1  (NUMERIC)
--     KIDS_USE_PV_MONTH1 → kids_use_pv_month1(NUMERIC)
--     NFX_USE_YN 'Y'/'N' → nfx_use_yn        (BOOLEAN)
-- ============================================================
INSERT INTO users (
    sha2_hash,
    age_grp10,
    inhome_rate,
    ch_hh_avg_month1,
    svod_scrb_cnt_grp,
    paid_chnl_cnt_grp,
    kids_use_pv_month1,
    nfx_use_yn
)
SELECT
    sha2_hash,
    "AGE_GRP10",
    -- INHOME_RATE: '50.0' → 50
    CASE WHEN "INHOME_RATE" ~ '^[0-9.]+$'
         THEN ROUND("INHOME_RATE"::NUMERIC)::SMALLINT
         ELSE NULL END,
    -- CH_HH_AVG_MONTH1: '14.1' → 14.10
    CASE WHEN "CH_HH_AVG_MONTH1" ~ '^[0-9.]+$'
         THEN ROUND("CH_HH_AVG_MONTH1"::NUMERIC, 2)
         ELSE NULL END,
    "SVOD_SCRB_CNT_GRP",
    "PAID_CHNL_CNT_GRP",
    -- KIDS_USE_PV_MONTH1: '0.0' → 0.0
    CASE WHEN "KIDS_USE_PV_MONTH1" ~ '^[0-9.]+$'
         THEN ROUND("KIDS_USE_PV_MONTH1"::NUMERIC, 1)
         ELSE NULL END,
    -- NFX_USE_YN: 'Y' → TRUE, 그 외 → FALSE
    ("NFX_USE_YN" = 'Y')
FROM user_table
ON CONFLICT (sha2_hash) DO NOTHING;

DO $$
DECLARE
    inserted BIGINT;
    staging  BIGINT;
BEGIN
    SELECT COUNT(*) INTO inserted FROM users;
    SELECT COUNT(*) INTO staging  FROM user_table;
    RAISE NOTICE '[STEP 1] 완료 - 스테이징: %, 삽입: %', staging, inserted;
END $$;


-- ============================================================
-- STEP 2. vod 마이그레이션
--   변환:
--     CT_CL              → ct_cl          (컬럼명 소문자)
--     disp_rtm_sec(text) → INTEGER        ('4860.0' → 4860)
--     director '-'       → NULL
--     smry 빈값          → NULL
-- ============================================================
INSERT INTO vod (
    full_asset_id,
    asset_nm,
    ct_cl,
    genre,
    genre_detail,
    provider,
    asset_prod,
    series_nm,
    disp_rtm,
    disp_rtm_sec,
    director,
    smry
)
SELECT
    full_asset_id,
    asset_nm,
    "CT_CL",
    NULLIF(TRIM(genre), ''),
    NULLIF(TRIM(genre_detail), ''),
    NULLIF(TRIM(provider), ''),
    NULLIF(TRIM(asset_prod), ''),
    NULLIF(TRIM(series_nm), ''),
    NULLIF(TRIM(disp_rtm), ''),
    -- disp_rtm_sec: '4860.0' → 4860
    CASE WHEN disp_rtm_sec ~ '^[0-9.]+$'
         THEN ROUND(disp_rtm_sec::NUMERIC)::INTEGER
         ELSE 0 END,
    -- director: '-' 또는 빈값 → NULL
    CASE WHEN TRIM(director) IN ('-', '', 'nan', 'NaN', 'NULL', 'null')
              OR director IS NULL
         THEN NULL
         ELSE TRIM(director) END,
    -- smry: 빈값 → NULL
    NULLIF(TRIM(smry), '')
FROM vod_table
ON CONFLICT (full_asset_id) DO NOTHING;

DO $$
DECLARE
    inserted BIGINT;
    staging  BIGINT;
BEGIN
    SELECT COUNT(*) INTO inserted FROM vod;
    SELECT COUNT(*) INTO staging  FROM vod_table;
    RAISE NOTICE '[STEP 2] 완료 - 스테이징: %, 삽입: %', staging, inserted;
END $$;


-- ============================================================
-- STEP 3. watch_history 마이그레이션
--   변환:
--     sha2_hash      → user_id_fk       (컬럼명 변경)
--     full_asset_id  → vod_id_fk        (컬럼명 변경)
--     strt_dt (text) → TIMESTAMP        ('2023-01-01 14:28:25')
--     use_tms (text) → INTEGER          ('2.0' → 2)
--     completion_rate→ NUMERIC(8,4)
--     satisfaction   → NUMERIC(8,4)
--
--   주의: UNIQUE(user_id_fk, vod_id_fk, strt_dt) 위반 시 → DO NOTHING
--   주의: users/vod에 없는 FK → 자동 제외 (WHERE EXISTS)
-- ============================================================
INSERT INTO watch_history (
    user_id_fk,
    vod_id_fk,
    strt_dt,
    use_tms,
    completion_rate,
    satisfaction
)
SELECT
    wh.sha2_hash,
    wh.full_asset_id,
    -- strt_dt: '2023-01-01 14:28:25' → TIMESTAMP
    wh.strt_dt::TIMESTAMP,
    -- use_tms: '411.0' → 411
    CASE WHEN wh.use_tms ~ '^[0-9.]+$'
         THEN ROUND(wh.use_tms::NUMERIC)::INTEGER
         ELSE 0 END,
    -- completion_rate: '0.0845...' → NUMERIC(8,4)
    CASE WHEN wh.completion_rate ~ '^[0-9.]+$'
         THEN ROUND(wh.completion_rate::NUMERIC, 4)
         ELSE 0.0 END,
    -- satisfaction: '0.0846...' → NUMERIC(8,4)
    CASE WHEN wh.satisfaction ~ '^[0-9.]+$'
         THEN ROUND(wh.satisfaction::NUMERIC, 4)
         ELSE 0.0 END
FROM watch_history_table wh
-- FK 무결성: users/vod에 없는 레코드 제외
WHERE EXISTS (SELECT 1 FROM users u WHERE u.sha2_hash    = wh.sha2_hash)
  AND EXISTS (SELECT 1 FROM vod   v WHERE v.full_asset_id = wh.full_asset_id)
ON CONFLICT (user_id_fk, vod_id_fk, strt_dt) DO NOTHING;

DO $$
DECLARE
    inserted BIGINT;
    staging  BIGINT;
    skipped  BIGINT;
BEGIN
    SELECT COUNT(*) INTO inserted FROM watch_history;
    SELECT COUNT(*) INTO staging  FROM watch_history_table;
    skipped := staging - inserted;
    RAISE NOTICE '[STEP 3] 완료 - 스테이징: %, 삽입: %, 스킵(중복/FK): %',
                 staging, inserted, skipped;
END $$;


-- ============================================================
-- STEP 4. 최종 검증
-- ============================================================
DO $$
DECLARE
    user_cnt    BIGINT;
    vod_cnt     BIGINT;
    wh_cnt      BIGINT;
    fk_user_err BIGINT;
    fk_vod_err  BIGINT;
    avg_sat     NUMERIC;
BEGIN
    SELECT COUNT(*) INTO user_cnt FROM users;
    SELECT COUNT(*) INTO vod_cnt  FROM vod;
    SELECT COUNT(*) INTO wh_cnt   FROM watch_history;

    -- FK 무결성 확인
    SELECT COUNT(*) INTO fk_user_err
    FROM watch_history wh
    WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.sha2_hash = wh.user_id_fk);

    SELECT COUNT(*) INTO fk_vod_err
    FROM watch_history wh
    WHERE NOT EXISTS (SELECT 1 FROM vod v WHERE v.full_asset_id = wh.vod_id_fk);

    -- 평균 만족도 확인 (기대: ~0.443)
    SELECT ROUND(AVG(satisfaction), 4) INTO avg_sat FROM watch_history;

    RAISE NOTICE '========================================';
    RAISE NOTICE '마이그레이션 결과';
    RAISE NOTICE '----------------------------------------';
    RAISE NOTICE 'users        : % 행 (기대: ~242,702)', user_cnt;
    RAISE NOTICE 'vod          : % 행 (기대: ~166,159)', vod_cnt;
    RAISE NOTICE 'watch_history: % 행 (기대: ~3,992,530)', wh_cnt;
    RAISE NOTICE '----------------------------------------';
    RAISE NOTICE 'FK 위반 (user): % 건 (기대: 0)', fk_user_err;
    RAISE NOTICE 'FK 위반 (vod) : % 건 (기대: 0)', fk_vod_err;
    RAISE NOTICE '평균 satisfaction: % (기대: ~0.443)', avg_sat;
    RAISE NOTICE '========================================';

    -- 치명적 오류 시 중단
    IF fk_user_err > 0 OR fk_vod_err > 0 THEN
        RAISE WARNING 'FK 무결성 위반이 있습니다. 데이터를 확인하세요.';
    END IF;
END $$;

-- Migration complete. Next: run schema/create_indexes.sql
