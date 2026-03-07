"""
결측치 보완 파이프라인 (TMDB API 버전)

대상:
  - vod.director: NULL 313건 → TMDB에서 감독명 검색
  - vod.smry:     NULL  28건 → TMDB에서 줄거리 검색

실행:
  set TMDB_API_KEY=your_api_key
  python pipeline/01_fill_missing.py

멱등성: rag_processed=FALSE 조건으로 재실행 안전
"""
import logging
import sys
import time

import requests

import config
from db import fetch_all_as_dict, get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
SESSION = requests.Session()
SESSION.params = {"api_key": config.TMDB_API_KEY, "language": "ko-KR"}


# ---------------------------------------------------------------------------
# TMDB 검색 헬퍼
# ---------------------------------------------------------------------------

def _search_tmdb(title: str, is_movie: bool) -> dict | None:
    """제목으로 TMDB 검색 → 첫 번째 결과 반환"""
    endpoint = "movie" if is_movie else "tv"
    try:
        resp = SESSION.get(
            f"{TMDB_BASE}/search/{endpoint}",
            params={"query": title},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None
    except Exception:
        return None


def _get_credits(tmdb_id: int, is_movie: bool) -> dict:
    """TMDB credits 조회 (감독, 주연)"""
    endpoint = "movie" if is_movie else "tv"
    try:
        resp = SESSION.get(
            f"{TMDB_BASE}/{endpoint}/{tmdb_id}/credits",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def _find_director(credits: dict) -> str | None:
    """credits에서 감독명 추출"""
    for member in credits.get("crew", []):
        if member.get("job") == "Director":
            return member.get("name")
    # TV의 경우 created_by에서 찾기
    for person in credits.get("created_by", []):
        return person.get("name")
    return None


def _search_vod(vod: dict) -> tuple[dict | None, bool]:
    """VOD 정보로 TMDB 검색 → (결과, is_movie)"""
    title = vod.get("asset_nm", "")
    ct_cl = vod.get("ct_cl", "")

    is_movie = "영화" in ct_cl

    # 1차: ct_cl 기반으로 검색
    result = _search_tmdb(title, is_movie)
    if result:
        return result, is_movie

    # 2차: 반대 타입으로 재검색
    result = _search_tmdb(title, not is_movie)
    if result:
        return result, not is_movie

    return None, is_movie


# ---------------------------------------------------------------------------
# director 결측치 보완
# ---------------------------------------------------------------------------

def process_missing_directors():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT full_asset_id, asset_nm, ct_cl, genre, genre_detail,
                       provider, release_date
                FROM vod
                WHERE director IS NULL
                  AND rag_processed = FALSE
                ORDER BY full_asset_id
            """)
            vods = fetch_all_as_dict(cur)

    if not vods:
        logger.info("director 결측치: 처리할 대상 없음")
        return

    logger.info(f"director 결측치: {len(vods)}건 처리 시작")
    success, skipped, failed = 0, 0, 0

    for i, vod in enumerate(vods, 1):
        try:
            result, is_movie = _search_vod(vod)
            director = None

            if result:
                tmdb_id = result.get("id")
                credits = _get_credits(tmdb_id, is_movie)
                director = _find_director(credits)

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE vod
                        SET director         = %s,
                            rag_processed    = TRUE,
                            rag_source       = 'TMDB',
                            rag_processed_at = NOW()
                        WHERE full_asset_id = %s
                    """, (director, vod["full_asset_id"]))

            if director:
                success += 1
            else:
                skipped += 1

            time.sleep(0.25)  # TMDB 레이트 리밋 (40req/10s)

        except Exception as e:
            failed += 1
            logger.error(f"  [오류] {vod['full_asset_id']} ({vod['asset_nm']}): {e}")

        if i % 50 == 0:
            logger.info(f"  진행: {i}/{len(vods)} (성공:{success}, 스킵:{skipped}, 실패:{failed})")

    logger.info(f"director 처리 완료 — 성공:{success}, 미발견:{skipped}, 오류:{failed}")


# ---------------------------------------------------------------------------
# smry 결측치 보완
# ---------------------------------------------------------------------------

def process_missing_smry():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT full_asset_id, asset_nm, ct_cl, genre, genre_detail,
                       director, cast_lead, release_date
                FROM vod
                WHERE smry IS NULL
                  AND rag_processed = FALSE
                ORDER BY full_asset_id
            """)
            vods = fetch_all_as_dict(cur)

    if not vods:
        logger.info("smry 결측치: 처리할 대상 없음")
        return

    logger.info(f"smry 결측치: {len(vods)}건 처리 시작")
    success, skipped, failed = 0, 0, 0

    for i, vod in enumerate(vods, 1):
        try:
            result, _ = _search_vod(vod)
            smry = None

            if result:
                smry = result.get("overview") or None
                if smry and len(smry.strip()) < 10:
                    smry = None  # 너무 짧은 줄거리 무시

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE vod
                        SET smry             = %s,
                            rag_processed    = TRUE,
                            rag_source       = 'TMDB',
                            rag_processed_at = NOW()
                        WHERE full_asset_id = %s
                    """, (smry, vod["full_asset_id"]))

            if smry:
                success += 1
            else:
                skipped += 1

            time.sleep(0.25)

        except Exception as e:
            failed += 1
            logger.error(f"  [오류] {vod['full_asset_id']} ({vod['asset_nm']}): {e}")

        if i % 10 == 0:
            logger.info(f"  진행: {i}/{len(vods)} (성공:{success}, 스킵:{skipped}, 실패:{failed})")

    logger.info(f"smry 처리 완료 — 성공:{success}, 미발견:{skipped}, 오류:{failed}")


# ---------------------------------------------------------------------------
# 검증 출력
# ---------------------------------------------------------------------------

def print_summary():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    rag_source,
                    COUNT(*) AS cnt,
                    SUM(CASE WHEN director IS NOT NULL THEN 1 ELSE 0 END) AS director_filled,
                    SUM(CASE WHEN smry IS NOT NULL THEN 1 ELSE 0 END) AS smry_filled
                FROM vod
                WHERE rag_processed = TRUE
                GROUP BY rag_source
                ORDER BY rag_source
            """)
            rows = cur.fetchall()

    logger.info("=== 처리 결과 요약 ===")
    for row in rows:
        logger.info(f"  {row[0]}: {row[1]}건 (director:{row[2]}, smry:{row[3]})")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not config.TMDB_API_KEY:
        logger.error("TMDB_API_KEY 환경변수가 설정되지 않았습니다.")
        logger.error("set TMDB_API_KEY=your_api_key")
        sys.exit(1)

    logger.info("=== 결측치 보완 파이프라인 시작 (TMDB) ===")
    process_missing_directors()
    process_missing_smry()
    print_summary()
    logger.info("=== 완료 ===")
