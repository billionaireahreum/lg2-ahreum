"""
결측치 보완 파이프라인 (TMDB API)

대상: vod.director IS NULL OR vod.smry IS NULL
소스: TMDB (ko-KR → en-US 폴백)

실행:
  set TMDB_API_KEY=your_api_key
  python pipeline/01_fill_missing.py

멱등성: director/smry 둘 다 단일 패스로 처리 → rag_processed 충돌 없음
"""
import logging
import re
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
SESSION_KO = requests.Session()
SESSION_KO.params = {"api_key": config.TMDB_API_KEY, "language": "ko-KR"}
SESSION_EN = requests.Session()
SESSION_EN.params = {"api_key": config.TMDB_API_KEY, "language": "en-US"}

PERSON_NAME_CACHE: dict[int, str | None] = {}  # person_id → 한국어 이름 캐시


# ---------------------------------------------------------------------------
# TMDB 헬퍼
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    """TMDB 검색 정확도를 높이기 위한 제목 전처리"""
    if not title:
        return ""
    t = title.strip()
    t = re.sub(r"\[[^\]]*\]", " ", t)          # [자막], [HD] 등 제거
    t = re.sub(r"\([^)]*\)", " ", t)            # (1부), (더빙) 등 제거
    t = re.sub(r"\b\d+\s*회\b", " ", t)        # 1회, 23회 등 제거
    t = re.sub(r"\b\d+\s*부\b", " ", t)        # 1부, 2부 제거
    t = re.sub(r"\b시즌\s*\d+\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bseason\s*\d+\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b더빙\b|\b자막\b|\bHD\b|\bUHD\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _search_tmdb(title: str, is_movie: bool, session: requests.Session,
                 release_year: str | None = None) -> dict | None:
    endpoint = "movie" if is_movie else "tv"
    try:
        resp = session.get(
            f"{TMDB_BASE}/search/{endpoint}",
            params={"query": title},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None

        # 연도 일치하는 후보 우선 선택
        if release_year:
            for r in results[:5]:
                date = r.get("release_date") or r.get("first_air_date") or ""
                if date.startswith(release_year):
                    return r

        return results[0]
    except Exception:
        return None


def _get_credits(tmdb_id: int, is_movie: bool) -> dict:
    endpoint = "movie" if is_movie else "tv"
    try:
        resp = SESSION_KO.get(f"{TMDB_BASE}/{endpoint}/{tmdb_id}/credits", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def _get_detail(tmdb_id: int, is_movie: bool) -> dict:
    """TMDB detail 조회 (TV created_by 등)"""
    endpoint = "movie" if is_movie else "tv"
    try:
        resp = SESSION_KO.get(f"{TMDB_BASE}/{endpoint}/{tmdb_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def _get_korean_name(person_id: int) -> str | None:
    """TMDB person API로 한국어 이름 조회 (캐시 적용)"""
    if person_id in PERSON_NAME_CACHE:
        return PERSON_NAME_CACHE[person_id]
    try:
        resp = SESSION_KO.get(f"{TMDB_BASE}/person/{person_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        name = None
        for aka in data.get("also_known_as", []):
            if aka and any('\uAC00' <= c <= '\uD7A3' for c in aka):
                name = aka
                break
        if not name:
            name = data.get("name")
        PERSON_NAME_CACHE[person_id] = name
        return name
    except Exception:
        PERSON_NAME_CACHE[person_id] = None
        return None


def _find_director(credits: dict, detail: dict | None = None) -> str | None:
    """crew에서 Director 추출 후 한국어 이름으로 변환"""
    for job in ("Director", "Series Director"):
        for member in credits.get("crew", []):
            if member.get("job") == job:
                person_id = member.get("id")
                if person_id:
                    return _get_korean_name(person_id)
                return member.get("name")
    if detail:
        for person in detail.get("created_by", []):
            person_id = person.get("id")
            if person_id:
                name = _get_korean_name(person_id)
                if name:
                    return name
    return None


def _infer_is_movie(ct_cl: str) -> bool:
    ct = (ct_cl or "").lower()
    if any(k in ct for k in ["영화", "movie", "극장판"]):
        return True
    if any(k in ct for k in ["드라마", "tv", "시리즈", "예능", "다큐", "애니", "키즈"]):
        return False
    return True


def _search_vod(vod: dict) -> tuple[dict | None, bool]:
    """VOD 제목으로 TMDB 검색 (정규화 후 movie/tv 양쪽 시도, 연도 우선)"""
    title = _normalize_title(vod.get("asset_nm", ""))
    is_movie = _infer_is_movie(vod.get("ct_cl", ""))
    release_year = str(vod.get("release_date") or "")[:4] or None

    result = _search_tmdb(title, is_movie, SESSION_KO, release_year)
    if result:
        return result, is_movie

    result = _search_tmdb(title, not is_movie, SESSION_KO, release_year)
    if result:
        return result, not is_movie

    return None, is_movie


def _get_smry(tmdb_id: int, is_movie: bool) -> str | None:
    """ko-KR overview → 없으면 en-US overview"""
    endpoint = "movie" if is_movie else "tv"
    for session in (SESSION_KO, SESSION_EN):
        try:
            resp = session.get(f"{TMDB_BASE}/{endpoint}/{tmdb_id}", timeout=10)
            resp.raise_for_status()
            overview = resp.json().get("overview", "").strip()
            if len(overview) >= 10:
                return overview
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Ollama 헬퍼 (smry 생성 폴백)
# ---------------------------------------------------------------------------

def _query_ollama(prompt: str) -> str | None:
    try:
        resp = requests.post(
            f"{config.OLLAMA_HOST}/api/generate",
            json={"model": config.OLLAMA_MODEL, "prompt": prompt, "stream": False, "temperature": 0.3},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        logger.warning(f"  Ollama 오류: {e}")
        return None


def _generate_smry_ollama(vod: dict, new_dir: str | None = None) -> str | None:
    director = new_dir or vod.get("director") or "미상"
    prompt = (
        f"다음 메타데이터만 바탕으로 한국어 2~3문장 소개문을 작성해줘.\n"
        f"확실하지 않은 세부 줄거리는 지어내지 말고, 일반적인 소개 수준으로만 작성해.\n"
        f"텍스트만 출력해.\n\n"
        f"영상명: {vod.get('asset_nm', '')}\n"
        f"장르: {vod.get('genre', '')} / {vod.get('genre_detail', '')}\n"
        f"감독: {director}\n"
        f"주연: {vod.get('cast_lead') or '미상'}\n"
        f"유형: {vod.get('ct_cl', '')}\n"
    )
    result = _query_ollama(prompt)
    if result and len(result.strip()) >= 10:
        return result.strip()
    return None


# ---------------------------------------------------------------------------
# 단일 패스 통합 처리
# ---------------------------------------------------------------------------

def process_missing_data():
    """director, smry 결측치를 한 번의 패스로 통합 처리"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT full_asset_id, asset_nm, ct_cl, genre, genre_detail,
                       director, smry, cast_lead, release_date
                FROM vod
                WHERE (director IS NULL OR smry IS NULL)
                  AND rag_processed = FALSE
                ORDER BY full_asset_id
            """)
            vods = fetch_all_as_dict(cur)

    if not vods:
        logger.info("처리할 결측치 없음")
        return

    logger.info(f"결측치 보완: {len(vods)}건 처리 시작")
    success_dir, success_smry, skipped, failed = 0, 0, 0, 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            for i, vod in enumerate(vods, 1):
                try:
                    needs_dir  = vod["director"] is None
                    needs_smry = vod["smry"] is None

                    result, is_movie = _search_vod(vod)

                    new_dir  = None
                    new_smry = None

                    rag_source = "TMDB"
                    if result:
                        tmdb_id = result["id"]

                        if needs_dir:
                            credits = _get_credits(tmdb_id, is_movie)
                            detail  = _get_detail(tmdb_id, is_movie)
                            new_dir = _find_director(credits, detail)

                        if needs_smry:
                            new_smry = _get_smry(tmdb_id, is_movie)

                    # TMDB에서 smry 못 찾으면 Ollama로 생성
                    if needs_smry and not new_smry:
                        new_smry = _generate_smry_ollama(vod, new_dir)
                        if new_smry:
                            rag_source = "TMDB+OLLAMA" if result else "OLLAMA"

                    cur.execute("""
                        UPDATE vod
                        SET director         = COALESCE(%s, director),
                            smry             = COALESCE(%s, smry),
                            rag_processed    = TRUE,
                            rag_source       = %s,
                            rag_processed_at = NOW()
                        WHERE full_asset_id = %s
                    """, (new_dir, new_smry, rag_source, vod["full_asset_id"]))

                    if new_dir:
                        success_dir += 1
                    if new_smry:
                        success_smry += 1
                    if not new_dir and not new_smry:
                        skipped += 1

                    conn.commit()
                    time.sleep(0.25)

                except Exception as e:
                    conn.rollback()
                    failed += 1
                    logger.error(f"  [오류] {vod['full_asset_id']} ({vod['asset_nm']}): {e}")

                if i % 50 == 0:
                    logger.info(
                        f"  진행: {i}/{len(vods)} "
                        f"(감독:{success_dir}, 줄거리:{success_smry}, 스킵:{skipped}, 실패:{failed})"
                    )

    logger.info(f"완료 — 감독:{success_dir}, 줄거리:{success_smry}, 스킵:{skipped}, 오류:{failed}")


# ---------------------------------------------------------------------------
# 요약 출력
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
        logger.info(f"  {row[0]}: {row[1]}건 (감독:{row[2]}, 줄거리:{row[3]})")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not config.TMDB_API_KEY:
        logger.error("TMDB_API_KEY 환경변수를 설정하세요: set TMDB_API_KEY=your_key")
        sys.exit(1)

    logger.info("=== 결측치 보완 파이프라인 시작 (TMDB) ===")
    process_missing_data()
    print_summary()
    logger.info("=== 완료 ===")
