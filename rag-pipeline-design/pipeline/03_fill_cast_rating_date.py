"""
시리즈 단위 메타데이터 보완 파이프라인 (TMDB API - append_to_response)

기존 row 단위 방식을 시리즈 단위로 완전 교체합니다.
normalized_title 기준으로 중복 row를 묶어 TMDB API를 시리즈당 1회만 호출하고,
같은 시리즈의 모든 row를 일괄 UPDATE 합니다.

개선 사항:
  - API 호출: ~110,507회 → ~22,414회 (5배 감소)
  - append_to_response: credits + 등급 정보를 1회 호출로 수집 (3회 → 1회)
  - tmdb_id DB 영구 저장: 세션 끊겨도 재호출 방지
  - tmdb_id = -1: 검색 실패 기록 → 재호출 영구 차단

체크포인트:
  - tmdb_id IS NULL → 미처리
  - tmdb_id = -1    → TMDB 검색 실패 (재호출 안 함)
  - tmdb_id > 0     → 처리 완료

신규 컬럼 (스크립트 최초 실행 시 자동 추가):
  ALTER TABLE vod ADD COLUMN tmdb_id         INT;   -- NULL=미처리, -1=미발견, >0=TMDB ID
  ALTER TABLE vod ADD COLUMN tmdb_media_type TEXT;  -- 'movie' / 'tv'
  ALTER TABLE vod ADD COLUMN rating_source   TEXT;  -- 'tmdb_kr' / 'tmdb_us' / 'rule_based'

실행:
  python pipeline/03_fill_cast_rating_date.py
"""
import logging
import re
import sys
import time
from typing import Optional

import requests
from kiwipiepy import Kiwi

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
# TMDB API 설정
# ---------------------------------------------------------------------------
TMDB_BASE = "https://api.themoviedb.org/3"
SESSION = requests.Session()
SESSION.params = {"api_key": config.TMDB_API_KEY, "language": "ko-KR"}

_API_CALL_COUNT: int = 0

# ---------------------------------------------------------------------------
# US → KR 등급 매핑 테이블
# ---------------------------------------------------------------------------
# MPAA(미국 영화) → 한국 영화진흥위원회 기준
US_MOVIE_RATING_MAP: dict[str, str] = {
    "G":     "전체관람가",
    "PG":    "12세이상관람가",
    "PG-13": "12세이상관람가",
    "R":     "15세이상관람가",
    "NC-17": "청소년관람불가",
}

# TV Parental Guidelines → 한국 방송통신위원회 기준
US_TV_RATING_MAP: dict[str, str] = {
    "TV-Y":  "전체관람가",
    "TV-Y7": "7세이상관람가",
    "TV-G":  "전체관람가",
    "TV-PG": "12세이상관람가",
    "TV-14": "15세이상관람가",
    "TV-MA": "청소년관람불가",
}

# ---------------------------------------------------------------------------
# Kiwi 형태소 분석기 (띄어쓰기 교정용)
# ---------------------------------------------------------------------------
_kiwi = Kiwi()


# ---------------------------------------------------------------------------
# 스키마 초기화: 신규 컬럼 자동 추가
# ---------------------------------------------------------------------------

def ensure_columns(conn) -> None:
    """
    vod 테이블에 필요한 컬럼이 없으면 자동으로 추가합니다.
    이미 존재하면 스킵합니다 (멱등성 보장).
    """
    columns_to_add = [
        ("tmdb_id",         "INT",  "NULL=미처리, -1=미발견, >0=TMDB ID"),
        ("tmdb_media_type", "TEXT", "movie / tv"),
        ("rating_source",   "TEXT", "tmdb_kr / tmdb_us / rule_based"),
    ]
    with conn.cursor() as cur:
        for col_name, col_type, comment in columns_to_add:
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'vod' AND column_name = %s
            """, (col_name,))
            if cur.fetchone() is None:
                cur.execute(f"ALTER TABLE vod ADD COLUMN {col_name} {col_type}")
                logger.info(f"컬럼 추가 완료: vod.{col_name} {col_type}  -- {comment}")
            else:
                logger.debug(f"컬럼 이미 존재 (스킵): vod.{col_name}")
    conn.commit()


# ---------------------------------------------------------------------------
# 제목 정규화 (시리즈 묶기용 — 컬럼에 저장하지 않고 스크립트에서만 사용)
# ---------------------------------------------------------------------------

def _add_spacing(title: str) -> str:
    """띄어쓰기 없는 한국어 제목에 형태소 분석 기반 공백 추가."""
    if " " in title:
        return title  # 이미 띄어쓰기 있으면 그대로
    try:
        tokens = _kiwi.tokenize(title)
        return " ".join(t.form for t in tokens)
    except Exception:
        return title


def normalize_title(title: str) -> str:
    """
    제목에서 화질·자막·회차·시즌 등 부가 정보를 제거하여 시리즈 대표 제목 반환.

    Examples:
        '겨울왕국 [4K][더빙]'       → '겨울왕국'
        '이상한 변호사 우영우 15회' → '이상한 변호사 우영우'
        '오징어 게임 시즌2'         → '오징어 게임'
        '해리포터(자막)'            → '해리포터'
    """
    t = title.strip()
    t = re.sub(r"\[[^\]]*\]", " ", t)                         # [자막], [HD] 등
    t = re.sub(r"\([^)]*\)", " ", t)                          # (1부), (더빙) 등
    t = re.sub(r"\b\d+\s*회\b", " ", t)                      # 1회, 23회
    t = re.sub(r"\b\d+\s*부\b", " ", t)                      # 1부, 2부
    t = re.sub(r"\b시즌\s*\d+\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bSeason\s*\d+\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b더빙\b|\b자막\b|\bHD\b|\bUHD\b|\b4K\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    t = _add_spacing(t)
    return t


# ---------------------------------------------------------------------------
# TMDB API 래퍼
# ---------------------------------------------------------------------------

def _tmdb_get(url: str, **kwargs) -> requests.Response:
    """TMDB API GET 요청. 레이트 리밋 보호를 위해 실제 호출 후 0.26초 대기."""
    global _API_CALL_COUNT
    resp = SESSION.get(url, timeout=10, **kwargs)
    _API_CALL_COUNT += 1
    resp.raise_for_status()
    time.sleep(0.26)  # TMDB 제한: 초당 ~3.8회 이하 유지
    return resp


# ---------------------------------------------------------------------------
# TMDB 검색
# ---------------------------------------------------------------------------

def search_tmdb(title: str, is_movie: bool) -> Optional[dict]:
    """
    TMDB에서 제목으로 콘텐츠 검색.

    매칭 우선순위:
      1) 제목 완전 일치 (공백 무시)
      2) 제목 포함 관계
      3) 첫 번째 결과 폴백

    Returns:
        TMDB 검색 결과 dict, 결과 없으면 None
    """
    endpoint = "movie" if is_movie else "tv"
    compact_query = re.sub(r"\s+", "", title.lower())

    try:
        resp = _tmdb_get(
            f"{TMDB_BASE}/search/{endpoint}",
            params={"query": title},
        )
        results = resp.json().get("results", [])
        if not results:
            return None

        # 1차: 완전 일치
        for r in results[:5]:
            cand = (r.get("title") if is_movie else r.get("name") or "").strip()
            if re.sub(r"\s+", "", cand.lower()) == compact_query:
                return r

        # 2차: 포함 관계
        for r in results[:5]:
            cand = (r.get("title") if is_movie else r.get("name") or "").strip()
            compact_cand = re.sub(r"\s+", "", cand.lower())
            if compact_query in compact_cand or compact_cand in compact_query:
                return r

        # 3차: 첫 번째 결과 폴백
        return results[0]

    except Exception as e:
        logger.debug(f"TMDB 검색 오류 ({title}): {e}")
        return None


def search_series(norm_title: str, ct_cl: str) -> tuple[Optional[dict], bool]:
    """
    시리즈 대표 제목으로 TMDB 검색.

    ct_cl 기반으로 movie/tv를 1차 결정하고, 실패 시 반대 유형으로 재시도합니다.

    Returns:
        (result, is_movie)  result가 None이면 검색 실패
    """
    is_movie = "영화" in ct_cl

    # 1차 시도: ct_cl 기반 유형
    result = search_tmdb(norm_title, is_movie)
    if result:
        return result, is_movie

    # 2차 시도: 반대 유형 (예: 영화로 분류됐지만 TV인 경우)
    result = search_tmdb(norm_title, not is_movie)
    if result:
        return result, not is_movie

    return None, is_movie


# ---------------------------------------------------------------------------
# TMDB 상세 조회 (append_to_response)
# ---------------------------------------------------------------------------

def fetch_tmdb_detail(tmdb_id: int, is_movie: bool) -> Optional[dict]:
    """
    TMDB 상세 조회 — append_to_response로 단 1회 API 호출.

    1회 호출로 수집하는 정보:
      - 기본 정보     : overview, release_date / first_air_date
      - credits       : cast (주연·조연), crew (감독)
      - 등급 정보     : 영화 → release_dates / TV → content_ratings

    Returns:
        상세 정보 dict (append 응답 포함), 실패 시 None
    """
    endpoint = "movie" if is_movie else "tv"
    append = "credits,release_dates" if is_movie else "credits,content_ratings"

    try:
        resp = _tmdb_get(
            f"{TMDB_BASE}/{endpoint}/{tmdb_id}",
            params={"append_to_response": append},
        )
        return resp.json()
    except Exception as e:
        logger.debug(f"TMDB 상세 조회 오류 (id={tmdb_id}): {e}")
        return None


# ---------------------------------------------------------------------------
# 메타데이터 추출
# ---------------------------------------------------------------------------

def extract_cast_lead(credits: dict, max_cast: int = 3) -> Optional[str]:
    """billing order 상위 3명 주연 추출 → '홍길동, 김철수, 이영희'"""
    cast = credits.get("cast", [])
    names = [c["name"] for c in cast[:max_cast] if c.get("name")]
    return ", ".join(names) if names else None


def extract_cast_guest(credits: dict, skip: int = 3, max_cast: int = 5) -> Optional[str]:
    """
    billing order 4~8위 추가 출연진 최대 5명 추출.

    주의: TMDB episode-level guest_stars와 다른 개념.
    시리즈/영화 레벨에서 대표 출연진 외 후순위 주요 배우를 저장하는 메타보강용 필드.
    """
    cast = credits.get("cast", [])
    names = [c["name"] for c in cast[skip:skip + max_cast] if c.get("name")]
    return ", ".join(names) if names else None


def extract_rating(detail: dict, is_movie: bool) -> tuple[Optional[str], Optional[str]]:
    """
    한국 시청 등급 추출 (KR 직접값 → US 매핑 순서).

    Returns:
        (rating, rating_source)
        rating_source: 'tmdb_kr' | 'tmdb_us' | None
    """
    if is_movie:
        entries = detail.get("release_dates", {}).get("results", [])

        # 1순위: KR 직접값
        for entry in entries:
            if entry.get("iso_3166_1") == "KR":
                for r in entry.get("release_dates", []):
                    cert = r.get("certification", "").strip()
                    if cert:
                        return cert, "tmdb_kr"

        # 2순위: US MPAA → KR 매핑
        for entry in entries:
            if entry.get("iso_3166_1") == "US":
                for r in entry.get("release_dates", []):
                    cert = r.get("certification", "").strip()
                    mapped = US_MOVIE_RATING_MAP.get(cert)
                    if mapped:
                        return mapped, "tmdb_us"

    else:  # TV
        entries = detail.get("content_ratings", {}).get("results", [])

        # 1순위: KR 직접값
        for entry in entries:
            if entry.get("iso_3166_1") == "KR":
                rating = entry.get("rating", "").strip()
                if rating:
                    return rating, "tmdb_kr"

        # 2순위: US TV Parental Guidelines → KR 매핑
        for entry in entries:
            if entry.get("iso_3166_1") == "US":
                rating = entry.get("rating", "").strip()
                mapped = US_TV_RATING_MAP.get(rating)
                if mapped:
                    return mapped, "tmdb_us"

    return None, None


def extract_all_metadata(detail: dict, is_movie: bool) -> dict:
    """
    TMDB 상세 조회 응답에서 필요한 모든 메타데이터 추출.

    Returns:
        {cast_lead, cast_guest, rating, rating_source, release_date}
    """
    credits = detail.get("credits", {})

    cast_lead  = extract_cast_lead(credits)
    cast_guest = extract_cast_guest(credits)

    rating, rating_source = extract_rating(detail, is_movie)

    key = "release_date" if is_movie else "first_air_date"
    release_date = detail.get(key) or None
    if release_date == "":
        release_date = None

    return {
        "cast_lead":     cast_lead,
        "cast_guest":    cast_guest,
        "rating":        rating,
        "rating_source": rating_source,
        "release_date":  release_date,
    }


# ---------------------------------------------------------------------------
# DB 조회 / 업데이트
# ---------------------------------------------------------------------------

def fetch_unprocessed_rows(conn) -> list[dict]:
    """
    tmdb_id IS NULL 인 미처리 row 전체 조회.

    - tmdb_id = -1 (검색 실패로 확정)은 제외 → 재호출 방지
    - tmdb_id > 0 (처리 완료)는 제외
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT full_asset_id, asset_nm, ct_cl
            FROM vod
            WHERE tmdb_id IS NULL
              AND is_active = TRUE
              AND ct_cl IN ('영화', 'TV드라마', 'TV애니메이션', '키즈', 'TV 연예/오락')
            ORDER BY ct_cl, asset_nm
        """)
        return fetch_all_as_dict(cur)


def group_by_series(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """
    row 목록을 (normalized_title, ct_cl) 기준으로 시리즈 단위로 묶음.

    동일 콘텐츠의 더빙/자막/HD/UHD 등 서비스 변형 row를 하나로 처리합니다.
    normalized_title은 DB에 저장하지 않고 이 함수에서만 계산·사용합니다.

    Returns:
        {
            (normalized_title, ct_cl): {
                "ids": [full_asset_id, ...],
                "sample_title": "원본 asset_nm 예시 (로깅용)"
            }
        }
    """
    groups: dict[tuple[str, str], dict] = {}
    for row in rows:
        norm = normalize_title(row["asset_nm"])
        key = (norm, row["ct_cl"])
        if key not in groups:
            groups[key] = {
                "ids": [],
                "sample_title": row["asset_nm"],
            }
        groups[key]["ids"].append(row["full_asset_id"])
    return groups


def update_series_rows(
    cur,
    full_asset_ids: list[str],
    tmdb_id: int,
    tmdb_media_type: str,
    cast_lead: Optional[str],
    cast_guest: Optional[str],
    rating: Optional[str],
    rating_source: Optional[str],
    release_date: Optional[str],
) -> None:
    """
    동일 시리즈에 속한 모든 row를 일괄 UPDATE.

    덮어쓰기 정책:
    - tmdb_id, tmdb_media_type, rating_source : 항상 기록 (체크포인트)
    - cast_lead, cast_guest, rating, release_date : COALESCE — 기존값 보존,
      NULL인 경우만 새 값으로 채움 (01번 스크립트 등으로 채워진 데이터 보호)
    """
    cur.execute("""
        UPDATE vod
        SET
            tmdb_id         = %s,
            tmdb_media_type = %s,
            cast_lead       = COALESCE(cast_lead,    %s),
            cast_guest      = COALESCE(cast_guest,   %s),
            rating          = COALESCE(rating,       %s),
            rating_source   = COALESCE(rating_source, %s),
            release_date    = COALESCE(release_date, %s::date),
            tmdb_checked_at = NOW()
        WHERE full_asset_id = ANY(%s)
    """, (
        tmdb_id,
        tmdb_media_type,
        cast_lead,
        cast_guest,
        rating,
        rating_source,
        release_date,
        full_asset_ids,
    ))


def mark_series_not_found(cur, full_asset_ids: list[str]) -> None:
    """
    검색 실패한 시리즈 전체에 tmdb_id = -1 기록.
    다음 실행 시 WHERE tmdb_id IS NULL 조건에서 제외 → 재호출 방지.
    """
    cur.execute("""
        UPDATE vod
        SET tmdb_id         = -1,
            tmdb_checked_at = NOW()
        WHERE full_asset_id = ANY(%s)
    """, (full_asset_ids,))


def store_tmdb_id_only(cur, full_asset_ids: list[str], tmdb_id: int, tmdb_media_type: str) -> None:
    """
    TMDB ID 검색은 성공했지만 상세 조회에 실패한 경우.
    tmdb_id만 기록해 재검색을 방지하고, 메타데이터는 추후 보완 가능하도록 남겨둡니다.
    """
    cur.execute("""
        UPDATE vod
        SET tmdb_id         = %s,
            tmdb_media_type = %s,
            tmdb_checked_at = NOW()
        WHERE full_asset_id = ANY(%s)
    """, (tmdb_id, tmdb_media_type, full_asset_ids))


# ---------------------------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------------------------

def run() -> None:
    """
    전체 파이프라인 실행.

    단계:
      1) 신규 컬럼 자동 추가 (tmdb_id, tmdb_media_type, rating_source)
      2) 미처리 row 전체 로드 → Python에서 시리즈 단위로 그룹핑
      3) 시리즈별 TMDB 검색 (1회) + 상세 조회 (1회, append_to_response)
      4) 동일 시리즈 모든 row 일괄 UPDATE
    """
    logger.info("=== 시리즈 단위 메타데이터 보완 시작 (TMDB append_to_response) ===")

    # 진행 카운터
    total_series      = 0
    total_rows        = 0
    found_series      = 0
    not_found_series  = 0
    detail_fail       = 0
    cnt_cast          = 0
    cnt_rating_kr     = 0
    cnt_rating_us     = 0
    cnt_date          = 0

    COMMIT_EVERY = 100  # N개 시리즈 처리마다 커밋

    with get_conn() as conn:
        # ── 1) 컬럼 자동 추가 ────────────────────────────────────────────
        ensure_columns(conn)

        # ── 2) 미처리 row 전체 로드 & 시리즈 그룹핑 ─────────────────────
        logger.info("미처리 row 로딩 중...")
        rows = fetch_unprocessed_rows(conn)
        if not rows:
            logger.info("처리할 row 없음. 종료.")
            return

        groups = group_by_series(rows)
        total_series = len(groups)
        total_rows   = len(rows)
        logger.info(
            f"총 미처리 row: {total_rows:,}건 → "
            f"고유 시리즈: {total_series:,}개 (그룹핑 완료)"
        )

        # ── 3~4) 시리즈별 TMDB 호출 + 일괄 UPDATE ───────────────────────
        with conn.cursor() as cur:
            for idx, ((norm_title, ct_cl), group) in enumerate(groups.items(), 1):
                ids    = group["ids"]
                sample = group["sample_title"]

                try:
                    # TMDB 검색 (1회)
                    result, is_movie = search_series(norm_title, ct_cl)

                    if result is None:
                        mark_series_not_found(cur, ids)
                        not_found_series += 1
                        logger.debug(f"  미발견: '{sample}' ({ct_cl})")
                        continue

                    tmdb_id         = result.get("id")
                    tmdb_media_type = "movie" if is_movie else "tv"

                    # TMDB 상세 조회 — append_to_response로 1회 처리 (1회)
                    detail = fetch_tmdb_detail(tmdb_id, is_movie)

                    if detail is None:
                        # 상세 조회 실패 → tmdb_id는 저장 (재검색 방지), 메타데이터 미입력
                        store_tmdb_id_only(cur, ids, tmdb_id, tmdb_media_type)
                        detail_fail += 1
                        logger.warning(f"  상세 조회 실패 (tmdb_id={tmdb_id}): '{sample}'")
                        continue

                    meta = extract_all_metadata(detail, is_movie)

                    update_series_rows(
                        cur,
                        ids,
                        tmdb_id         = tmdb_id,
                        tmdb_media_type = tmdb_media_type,
                        cast_lead       = meta["cast_lead"],
                        cast_guest      = meta["cast_guest"],
                        rating          = meta["rating"],
                        rating_source   = meta["rating_source"],
                        release_date    = meta["release_date"],
                    )

                    found_series += 1
                    if meta["cast_lead"]:    cnt_cast += 1
                    if meta["rating"]:
                        if meta["rating_source"] == "tmdb_kr":
                            cnt_rating_kr += 1
                        else:
                            cnt_rating_us += 1
                    if meta["release_date"]: cnt_date += 1

                except Exception as e:
                    logger.error(f"[오류] '{sample}' ({ct_cl}): {e}")
                    # 오류 발생 시 tmdb_id = -1 기록 → 재시도 무한루프 방지
                    try:
                        mark_series_not_found(cur, ids)
                    except Exception:
                        pass

                # ── 주기적 커밋 + 진행 로그 ──────────────────────────────
                if idx % COMMIT_EVERY == 0:
                    conn.commit()
                    pct = idx / total_series * 100
                    logger.info(
                        f"  [{idx:,}/{total_series:,}] {pct:.1f}% | "
                        f"발견:{found_series:,} 미발견:{not_found_series:,} 상세실패:{detail_fail} | "
                        f"cast:{cnt_cast:,} rating(KR):{cnt_rating_kr:,} rating(US매핑):{cnt_rating_us:,} "
                        f"date:{cnt_date:,} | API:{_API_CALL_COUNT:,}회"
                    )

            conn.commit()  # 나머지 커밋

    logger.info("=" * 60)
    logger.info("=== 완료 ===")
    logger.info(f"  고유 시리즈 처리     : {total_series:,}개")
    logger.info(f"  대상 row 수          : {total_rows:,}건")
    logger.info(f"  TMDB 발견            : {found_series:,}개 시리즈")
    logger.info(f"  TMDB 미발견          : {not_found_series:,}개 시리즈")
    logger.info(f"  상세 조회 실패       : {detail_fail}개 시리즈")
    logger.info(f"  cast_lead 채움       : {cnt_cast:,}개 시리즈")
    logger.info(f"  rating 채움 (KR)     : {cnt_rating_kr:,}개 시리즈")
    logger.info(f"  rating 채움 (US매핑) : {cnt_rating_us:,}개 시리즈")
    logger.info(f"  release_date 채움    : {cnt_date:,}개 시리즈")
    logger.info(f"  실제 API 호출        : {_API_CALL_COUNT:,}회")
    logger.info("=" * 60)


if __name__ == "__main__":
    if not config.TMDB_API_KEY:
        logger.error("TMDB_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    run()
