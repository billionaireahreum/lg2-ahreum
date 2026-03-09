"""
cast_lead / cast_guest / rating / release_date 보완 파이프라인 (TMDB API)

대상:
  - vod.cast_lead   : TMDB cast에서 주연 3명 추출
  - vod.cast_guest  : TMDB cast에서 조연 최대 5명 추출
  - vod.rating      : TMDB release_dates/content_ratings에서 한국 등급
  - vod.release_date: TMDB에서 개봉/방영일 추출

멱등성:
  - tmdb_checked_at IS NULL 인 경우만 처리
  - 조회 성공/실패 여부와 관계없이 1회 시도 후 tmdb_checked_at 기록
  - 재실행 시 이미 조회 시도한 건 자동 스킵

실행:
  python pipeline/03_fill_cast_rating_date.py
"""
import logging
import re
import sys
import time

import requests
from kiwipiepy import Kiwi

import config
from db import fetch_all_as_dict, get_conn

_kiwi = Kiwi()

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
# 제목 정규화
# ---------------------------------------------------------------------------

def _add_spacing(title: str) -> str:
    """띄어쓰기 없는 한국어 제목에 자동 공백 추가"""
    if " " in title:
        return title  # 이미 띄어쓰기 있으면 그대로
    try:
        tokens = _kiwi.tokenize(title)
        return " ".join(t.form for t in tokens)
    except Exception:
        return title


def _normalize_title(title: str) -> str:
    t = title.strip()
    t = re.sub(r"\[[^\]]*\]", " ", t)           # [자막], [HD] 등 제거
    t = re.sub(r"\([^)]*\)", " ", t)             # (1부), (더빙) 등 제거
    t = re.sub(r"\b\d+\s*회\b", " ", t)         # 1회, 23회 제거
    t = re.sub(r"\b\d+\s*부\b", " ", t)         # 1부, 2부 제거
    t = re.sub(r"\b시즌\s*\d+\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bseason\s*\d+\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b더빙\b|\b자막\b|\bHD\b|\bUHD\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    t = _add_spacing(t)                          # 띄어쓰기 자동 교정
    return t


# ---------------------------------------------------------------------------
# TMDB 검색 헬퍼
# ---------------------------------------------------------------------------

def _search_tmdb(title: str, is_movie: bool) -> dict | None:
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


def _search_vod(vod: dict) -> tuple[dict | None, bool]:
    raw_title  = (vod.get("asset_nm") or "").strip()
    norm_title = _normalize_title(raw_title)
    is_movie   = "영화" in (vod.get("ct_cl") or "")

    # 원제목 우선, 실패 시 정규화 제목 시도
    candidate_titles = [raw_title]
    if norm_title and norm_title != raw_title:
        candidate_titles.append(norm_title)

    for title in candidate_titles:
        result = _search_tmdb(title, is_movie)
        if result:
            return result, is_movie

    for title in candidate_titles:
        result = _search_tmdb(title, not is_movie)
        if result:
            return result, not is_movie

    return None, is_movie


def _get_credits(tmdb_id: int, is_movie: bool) -> dict:
    endpoint = "movie" if is_movie else "tv"
    try:
        resp = SESSION.get(f"{TMDB_BASE}/{endpoint}/{tmdb_id}/credits", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def _get_release_dates(tmdb_id: int, is_movie: bool) -> dict:
    """한국 시청등급 조회"""
    try:
        if is_movie:
            resp = SESSION.get(
                f"{TMDB_BASE}/movie/{tmdb_id}/release_dates", timeout=10
            )
            resp.raise_for_status()
            for entry in resp.json().get("results", []):
                if entry.get("iso_3166_1") == "KR":
                    for r in entry.get("release_dates", []):
                        if r.get("certification"):
                            return {"rating": r["certification"]}
        else:
            resp = SESSION.get(
                f"{TMDB_BASE}/tv/{tmdb_id}/content_ratings", timeout=10
            )
            resp.raise_for_status()
            for entry in resp.json().get("results", []):
                if entry.get("iso_3166_1") == "KR":
                    return {"rating": entry.get("rating", "")}
    except Exception:
        pass
    return {}


def _extract_cast_lead(credits: dict, max_cast: int = 3) -> str | None:
    """주연 배우 최대 3명 추출 → '홍길동, 김철수, 이영희'"""
    cast = credits.get("cast", [])
    names = [c["name"] for c in cast[:max_cast] if c.get("name")]
    return ", ".join(names) if names else None


def _extract_cast_guest(credits: dict, skip: int = 3, max_cast: int = 5) -> str | None:
    """조연 배우 4~8번째 추출 → '홍길동, 김철수, ...'"""
    cast = credits.get("cast", [])
    names = [c["name"] for c in cast[skip:skip + max_cast] if c.get("name")]
    return ", ".join(names) if names else None


def _extract_release_date(result: dict, is_movie: bool) -> str | None:
    """개봉/방영일 추출"""
    key = "release_date" if is_movie else "first_air_date"
    val = result.get(key, "")
    return val if val else None


# ---------------------------------------------------------------------------
# 메인 처리
# ---------------------------------------------------------------------------

def fetch_unprocessed(batch_size: int = 500) -> list[dict]:
    """아직 TMDB 조회 안 한 VOD 조회 (tmdb_checked_at IS NULL)
    영화/드라마/애니메이션 우선 처리 (TMDB 매칭 가능성 높음)
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT full_asset_id, asset_nm, ct_cl
                FROM vod
                WHERE tmdb_checked_at IS NULL
                  AND is_active = TRUE
                  AND ct_cl IN ('영화', 'TV드라마', 'TV애니메이션')
                ORDER BY ct_cl, full_asset_id
                LIMIT %s
            """, (batch_size,))
            return fetch_all_as_dict(cur)


def update_vod(full_asset_id: str, cast_lead, cast_guest, rating, release_date):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE vod
                SET cast_lead        = %s,
                    cast_guest       = %s,
                    rating           = %s,
                    release_date     = %s::date,
                    tmdb_checked_at  = NOW()
                WHERE full_asset_id = %s
            """, (cast_lead, cast_guest, rating, release_date, full_asset_id))


def run():
    total_processed = 0
    total_cast = 0
    total_guest = 0
    total_rating = 0
    total_date = 0
    total_not_found = 0

    logger.info("=== cast_lead / cast_guest / rating / release_date 보완 시작 ===")

    BATCH = 500
    while True:
        vods = fetch_unprocessed(BATCH)
        if not vods:
            break

        logger.info(f"처리 배치: {len(vods)}건 (누적: {total_processed}건)")

        for i, vod in enumerate(vods, 1):
            try:
                result, is_movie = _search_vod(vod)

                cast_lead = None
                cast_guest = None
                rating = None
                release_date = None

                if result:
                    tmdb_id = result.get("id")
                    credits = _get_credits(tmdb_id, is_movie)
                    rating_data = _get_release_dates(tmdb_id, is_movie)

                    cast_lead    = _extract_cast_lead(credits)
                    cast_guest   = _extract_cast_guest(credits)
                    rating       = rating_data.get("rating") or None
                    release_date = _extract_release_date(result, is_movie)

                    if cast_lead:    total_cast   += 1
                    if cast_guest:   total_guest  += 1
                    if rating:       total_rating += 1
                    if release_date: total_date   += 1
                else:
                    total_not_found += 1

                update_vod(vod["full_asset_id"], cast_lead, cast_guest, rating, release_date)
                total_processed += 1
                time.sleep(0.26)  # TMDB 레이트 리밋 (40req/10s)

                if i % 100 == 0:
                    logger.info(
                        f"  [{i}/{len(vods)}] 누적:{total_processed} "
                        f"cast:{total_cast} guest:{total_guest} "
                        f"rating:{total_rating} date:{total_date} "
                        f"미발견:{total_not_found}"
                    )

            except Exception as e:
                logger.error(f"[오류] {vod['full_asset_id']} ({vod['asset_nm']}): {e}")

        logger.info(
            f"  누적 결과 → cast:{total_cast} / rating:{total_rating} "
            f"/ date:{total_date} / TMDB미발견:{total_not_found}"
        )

    logger.info("=== 완료 ===")
    logger.info(f"  전체 처리    : {total_processed:,}건")
    logger.info(f"  cast_lead 채움: {total_cast:,}건")
    logger.info(f"  cast_guest 채움: {total_guest:,}건")
    logger.info(f"  rating 채움   : {total_rating:,}건")
    logger.info(f"  release_date  : {total_date:,}건")
    logger.info(f"  TMDB 미발견   : {total_not_found:,}건")


if __name__ == "__main__":
    if not config.TMDB_API_KEY:
        logger.error("TMDB_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    run()
