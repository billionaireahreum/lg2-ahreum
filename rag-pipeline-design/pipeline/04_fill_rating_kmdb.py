"""
rating 보완 파이프라인 (KMDB API)

대상:
  - vod.rating : TMDB에서 등급을 가져오지 못한 국내 영화/드라마
                 → KMDB (한국영화데이터베이스) API로 관람등급 보완

전략:
  - TMDB 처리 완료(tmdb_checked_at IS NOT NULL) + rating IS NULL 건만 대상
  - ct_cl IN ('영화', 'TV드라마', 'TV애니메이션') + 국내 콘텐츠 우선
  - 일일 API 호출 제한 1,000회 → 하루 최대 처리 건 = 약 1,000건

멱등성:
  - kmdb_checked_at IS NULL 인 경우만 처리
  - 조회 성공/실패 무관하게 1회 시도 후 kmdb_checked_at 기록
  - 재실행 시 이미 시도한 건 자동 스킵

실행:
  python pipeline/04_fill_rating_kmdb.py

주의:
  - KMDB_SERVICE_KEY 환경변수 필요
  - KMDB API 일일 호출 제한: 약 1,000회 (하루 1회 실행 권장)
"""

from __future__ import annotations

import logging
import re
import sys
import time
from typing import Optional

import requests

import config
from db import fetch_all_as_dict, get_conn

# ---------------------------------------------------------------------------
# 로깅 설정
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# KMDB API 설정
# ---------------------------------------------------------------------------
KMDB_BASE = "http://api.koreafilm.or.kr/openapi-data2/wisenut/search_api/search_json2.jsp"
KMDB_SERVICE_KEY: str = config.KMDB_SERVICE_KEY  # pipeline/.env → KMDB_SERVICE_KEY

# 실제 API 호출 횟수 및 캐시 카운터
_API_CALL_COUNT: int = 0
_CACHE_HIT_COUNT: int = 0

# 인메모리 캐시: 제목 → 등급 (같은 시리즈 반복 호출 방지)
_RATING_CACHE: dict[str, Optional[str]] = {}

# KMDB API 레이트 리밋 대기 (초)
# 일일 1,000회 제한 → 1초에 1회 이하로 유지
SLEEP_SEC: float = 1.1

# 하루 최대 API 호출 횟수 (안전 마진 포함)
DAILY_LIMIT: int = 950


# ---------------------------------------------------------------------------
# 제목 정규화 (03_fill_cast_rating_date.py와 동일한 전처리)
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    """TMDB 검색과 동일한 정규화 규칙 적용."""
    t = title.strip()
    t = re.sub(r"\[[^\]]*\]", " ", t)            # [자막], [HD] 등 제거
    t = re.sub(r"\([^)]*\)", " ", t)             # (1부), (더빙) 등 제거
    t = re.sub(r"\b\d+\s*회\b", " ", t)          # 1회, 23회 제거
    t = re.sub(r"\b\d+\s*부\b", " ", t)          # 1부, 2부 제거
    t = re.sub(r"\b시즌\s*\d+\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bseason\s*\d+\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b더빙\b|\b자막\b|\bHD\b|\bUHD\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ---------------------------------------------------------------------------
# KMDB API 호출
# ---------------------------------------------------------------------------

def _kmdb_search(title: str) -> Optional[str]:
    """KMDB API로 제목 검색 → 대표관람등급(rating) 반환.

    Args:
        title: 검색할 VOD 제목 (정규화 후)

    Returns:
        관람등급 문자열 (예: '15세이상관람가') 또는 None
    """
    global _API_CALL_COUNT

    # 캐시 확인
    cache_key = re.sub(r"\s+", "", title.lower())
    if cache_key in _RATING_CACHE:
        global _CACHE_HIT_COUNT
        _CACHE_HIT_COUNT += 1
        return _RATING_CACHE[cache_key]

    rating: Optional[str] = None
    try:
        params = {
            "ServiceKey": KMDB_SERVICE_KEY,
            "collection": "kmdb_new2",
            "title": title,
            "detail": "Y",          # 상세 정보 포함 (rating 필드 포함)
            "listCount": "5",       # 최대 5개 후보
            "nation": "한국",       # 한국 콘텐츠 우선 필터
        }
        resp = requests.get(KMDB_BASE, params=params, timeout=15)
        _API_CALL_COUNT += 1
        resp.raise_for_status()
        time.sleep(SLEEP_SEC)   # 레이트 리밋 대기 (실제 호출 직후만)

        data = resp.json()
        results = (
            data.get("Data", [{}])[0]
                .get("Result", [])
        )

        if not results:
            _RATING_CACHE[cache_key] = None
            return None

        # 1차: 제목 완전 일치 후보 우선
        compact_query = re.sub(r"\s+", "", title.lower())
        matched = None
        for r in results[:5]:
            # KMDB 제목에는 !HS ... !HE 마크업이 붙을 수 있음 → 제거
            cand_title = re.sub(r"!HS|!HE", "", r.get("title", "")).strip()
            compact_cand = re.sub(r"\s+", "", cand_title.lower())
            if compact_cand == compact_query:
                matched = r
                break

        # 2차: 첫 번째 결과 폴백
        if matched is None:
            matched = results[0]

        raw_rating: str = matched.get("rating", "").strip()
        rating = raw_rating if raw_rating else None

    except Exception as e:
        logger.warning(f"KMDB API 오류 (title={title!r}): {e}")
        time.sleep(SLEEP_SEC)  # 오류 시에도 레이트 리밋 대기

    _RATING_CACHE[cache_key] = rating
    return rating


# ---------------------------------------------------------------------------
# DB 작업
# ---------------------------------------------------------------------------

def _ensure_kmdb_column(conn) -> None:
    """kmdb_checked_at 컬럼이 없으면 추가 (멱등성 보장)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'vod'
              AND column_name = 'kmdb_checked_at'
        """)
        if cur.fetchone() is None:
            logger.info("kmdb_checked_at 컬럼 추가 중...")
            cur.execute("""
                ALTER TABLE vod
                ADD COLUMN kmdb_checked_at TIMESTAMP;
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_vod_kmdb_checked_at
                    ON vod (kmdb_checked_at)
                    WHERE kmdb_checked_at IS NULL;
            """)
            conn.commit()
            logger.info("kmdb_checked_at 컬럼 및 인덱스 추가 완료.")
        else:
            logger.info("kmdb_checked_at 컬럼 이미 존재. 스킵.")


def fetch_unprocessed(conn, batch_size: int = 500) -> list[dict]:
    """KMDB 미조회 VOD 조회.

    조건:
      - rating IS NULL                    : 등급 없음
      - tmdb_checked_at IS NOT NULL       : TMDB는 이미 시도한 건
      - kmdb_checked_at IS NULL           : KMDB 미조회
      - is_active = TRUE
      - ct_cl 영화/드라마/애니메이션
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT full_asset_id, asset_nm, ct_cl
            FROM vod
            WHERE rating IS NULL
              AND tmdb_checked_at IS NOT NULL
              AND kmdb_checked_at IS NULL
              AND is_active = TRUE
              AND ct_cl IN ('영화', 'TV드라마', 'TV애니메이션')
            ORDER BY ct_cl, full_asset_id
            LIMIT %s
        """, (batch_size,))
        return fetch_all_as_dict(cur)


def update_vod_rating(cur, full_asset_id: str, rating: Optional[str]) -> None:
    """rating + kmdb_checked_at 업데이트. 커밋은 호출자에서 배치 단위로."""
    cur.execute("""
        UPDATE vod
        SET rating           = %s,
            kmdb_checked_at  = NOW()
        WHERE full_asset_id = %s
    """, (rating, full_asset_id))


# ---------------------------------------------------------------------------
# 메인 처리
# ---------------------------------------------------------------------------

def run() -> None:
    total_processed: int = 0
    total_filled: int = 0
    total_not_found: int = 0

    logger.info("=== rating 보완 시작 (KMDB API) ===")
    logger.info(f"일일 호출 제한: {DAILY_LIMIT}회 / sleep: {SLEEP_SEC}초")

    BATCH = 200  # KMDB 일일 제한 고려 → 소규모 배치

    with get_conn() as conn:
        _ensure_kmdb_column(conn)

        while True:
            # 일일 한도 초과 시 조기 종료
            if _API_CALL_COUNT >= DAILY_LIMIT:
                logger.warning(
                    f"일일 API 호출 한도 도달 ({_API_CALL_COUNT}회). 오늘은 여기까지."
                )
                break

            conn.commit()
            vods = fetch_unprocessed(conn, BATCH)
            if not vods:
                logger.info("더 이상 처리할 VOD가 없습니다.")
                break

            logger.info(
                f"처리 배치: {len(vods)}건 (누적: {total_processed}건 | "
                f"api호출: {_API_CALL_COUNT}회)"
            )

            with conn.cursor() as cur:
                for i, vod in enumerate(vods, 1):
                    # 배치 중간에도 한도 체크
                    if _API_CALL_COUNT >= DAILY_LIMIT:
                        logger.warning(
                            f"[{i}/{len(vods)}] 일일 한도 도달. 배치 중단."
                        )
                        conn.commit()
                        break

                    try:
                        raw_title  = (vod.get("asset_nm") or "").strip()
                        norm_title = _normalize_title(raw_title)

                        # 정규화 제목 우선, 같으면 원제목만 시도
                        titles_to_try = (
                            [norm_title, raw_title]
                            if norm_title != raw_title
                            else [raw_title]
                        )

                        rating: Optional[str] = None
                        for t in titles_to_try:
                            rating = _kmdb_search(t)
                            if rating:
                                break

                        if rating:
                            total_filled += 1
                        else:
                            total_not_found += 1

                        update_vod_rating(cur, vod["full_asset_id"], rating)
                        total_processed += 1

                        if i % 50 == 0:
                            conn.commit()
                            logger.info(
                                f"  [{i}/{len(vods)}] 누적:{total_processed} "
                                f"등급채움:{total_filled} 미발견:{total_not_found} | "
                                f"api호출:{_API_CALL_COUNT} 캐시히트:{_CACHE_HIT_COUNT}"
                            )

                    except Exception as e:
                        logger.error(
                            f"[오류] {vod['full_asset_id']} "
                            f"({vod.get('asset_nm', '')}): {e}"
                        )

                conn.commit()  # 배치 잔여분 커밋

            logger.info(
                f"  배치 완료 → 등급채움:{total_filled} / "
                f"미발견:{total_not_found} | api호출:{_API_CALL_COUNT}회"
            )

    # 최종 요약
    logger.info("=== 완료 ===")
    logger.info(f"  전체 처리     : {total_processed:,}건")
    logger.info(f"  rating 채움  : {total_filled:,}건")
    logger.info(f"  KMDB 미발견  : {total_not_found:,}건")
    logger.info(f"  실제 API 요청: {_API_CALL_COUNT:,}회")
    logger.info(f"  캐시 히트     : {_CACHE_HIT_COUNT:,}회")
    if total_processed > 0:
        fill_rate = total_filled / total_processed * 100
        logger.info(f"  등급 채움률  : {fill_rate:.1f}%")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not KMDB_SERVICE_KEY:
        logger.error(
            "KMDB_SERVICE_KEY 환경변수가 설정되지 않았습니다.\n"
            "  Windows: set KMDB_SERVICE_KEY=발급받은키\n"
            "  Linux:   export KMDB_SERVICE_KEY=발급받은키"
        )
        sys.exit(1)

    run()
