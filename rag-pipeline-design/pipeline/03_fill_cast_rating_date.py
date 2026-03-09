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
# 인메모리 캐시 (같은 작품 회차 반복 호출 방지)
# key: (endpoint, compact_title) → search 결과
# key: (endpoint, tmdb_id)       → credits / rating 결과
# ---------------------------------------------------------------------------
_SEARCH_CACHE: dict = {}
_CREDITS_CACHE: dict = {}
_RATING_CACHE: dict = {}


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
    compact_query = re.sub(r"\s+", "", title.lower())
    cache_key = (endpoint, compact_query)

    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key]

    result = None
    try:
        resp = SESSION.get(
            f"{TMDB_BASE}/search/{endpoint}",
            params={"query": title},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if results:
            # 1차: 완전 일치
            for r in results[:5]:
                cand = (r.get("title") if is_movie else r.get("name") or "").strip()
                if re.sub(r"\s+", "", cand.lower()) == compact_query:
                    result = r
                    break

            # 2차: 포함 관계
            if result is None:
                for r in results[:5]:
                    cand = (r.get("title") if is_movie else r.get("name") or "").strip()
                    compact_cand = re.sub(r"\s+", "", cand.lower())
                    if compact_query in compact_cand or compact_cand in compact_query:
                        result = r
                        break

            # 3차: 첫 번째 결과 폴백
            if result is None:
                result = results[0]

    except Exception:
        pass

    _SEARCH_CACHE[cache_key] = result  # None도 캐싱 (재검색 방지)
    return result


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
    cache_key = (endpoint, tmdb_id)

    if cache_key in _CREDITS_CACHE:
        return _CREDITS_CACHE[cache_key]

    try:
        resp = SESSION.get(f"{TMDB_BASE}/{endpoint}/{tmdb_id}/credits", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        data = {}

    _CREDITS_CACHE[cache_key] = data
    return data


def _get_release_dates(tmdb_id: int, is_movie: bool) -> dict:
    """한국 시청등급 조회"""
    endpoint = "movie" if is_movie else "tv"
    cache_key = (endpoint, tmdb_id)

    if cache_key in _RATING_CACHE:
        return _RATING_CACHE[cache_key]

    data = {}
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
                            data = {"rating": r["certification"]}
                            break
        else:
            resp = SESSION.get(
                f"{TMDB_BASE}/tv/{tmdb_id}/content_ratings", timeout=10
            )
            resp.raise_for_status()
            for entry in resp.json().get("results", []):
                if entry.get("iso_3166_1") == "KR":
                    data = {"rating": entry.get("rating", "")}
                    break
    except Exception:
        pass

    _RATING_CACHE[cache_key] = data
    return data


def _extract_cast_lead(credits: dict, max_cast: int = 3) -> str | None:
    """billing order 상위 3명 추출 (대표 출연진) → '홍길동, 김철수, 이영희'"""
    cast = credits.get("cast", [])
    names = [c["name"] for c in cast[:max_cast] if c.get("name")]
    return ", ".join(names) if names else None


def _extract_cast_guest(credits: dict, skip: int = 3, max_cast: int = 5) -> str | None:
    """추가 출연진 최대 5명 추출 (billing order 4~8위).

    주의: TMDB episode-level guest_stars와 다른 개념.
    시리즈/영화 레벨에서 대표 출연진 외 후순위 주요 배우를 저장하는 메타보강용 필드.
    실제 '게스트 출연자'가 아닌 'additional/supporting cast' 의미로 사용.
    """
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
    total_cache_hits = 0

    logger.info("=== cast_lead / cast_guest / rating / release_date 보완 시작 (캐싱 버전) ===")

    BATCH = 500
    while True:
        vods = fetch_unprocessed(BATCH)
        if not vods:
            break

        logger.info(f"처리 배치: {len(vods)}건 (누적: {total_processed}건)")

        for i, vod in enumerate(vods, 1):
            try:
                # 캐시 히트 여부 확인 (search 함수 호출 전 캐시 크기 스냅샷)
                cache_size_before = len(_SEARCH_CACHE)

                result, is_movie = _search_vod(vod)

                # search 캐시가 늘지 않았으면 캐시 히트
                is_cache_hit = len(_SEARCH_CACHE) == cache_size_before

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

                if is_cache_hit:
                    total_cache_hits += 1
                else:
                    time.sleep(0.26)  # 실제 API 호출 시에만 레이트 리밋 대기

                if i % 100 == 0:
                    logger.info(
                        f"  [{i}/{len(vods)}] 누적:{total_processed} "
                        f"cast:{total_cast} guest:{total_guest} "
                        f"rating:{total_rating} date:{total_date} "
                        f"미발견:{total_not_found} 캐시히트:{total_cache_hits}"
                    )

            except Exception as e:
                logger.error(f"[오류] {vod['full_asset_id']} ({vod['asset_nm']}): {e}")

        logger.info(
            f"  누적 결과 → cast:{total_cast} / rating:{total_rating} "
            f"/ date:{total_date} / TMDB미발견:{total_not_found} / 캐시히트:{total_cache_hits}"
        )

    logger.info("=== 완료 ===")
    logger.info(f"  전체 처리    : {total_processed:,}건")
    logger.info(f"  cast_lead 채움: {total_cast:,}건")
    logger.info(f"  cast_guest 채움: {total_guest:,}건")
    logger.info(f"  rating 채움   : {total_rating:,}건")
    logger.info(f"  release_date  : {total_date:,}건")
    logger.info(f"  TMDB 미발견   : {total_not_found:,}건")
    logger.info(f"  캐시 히트(절약): {total_cache_hits:,}건")


if __name__ == "__main__":
    if not config.TMDB_API_KEY:
        logger.error("TMDB_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    run()
