"""
결측치 보완 파이프라인

대상:
  - vod.director: NULL 313건 → Claude 추론 (제목+장르+제공사 기반)
  - vod.smry:     NULL  28건 → Claude 생성 (제목+장르+감독+주연 기반)

실행:
  python pipeline/01_fill_missing.py

멱등성: rag_processed=FALSE 조건으로 재실행 안전
"""
import logging
import sys

import anthropic

import config
from db import fetch_all_as_dict, get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


# ---------------------------------------------------------------------------
# 프롬프트 빌더
# ---------------------------------------------------------------------------

def _prompt_director(vod: dict) -> str:
    return f"""다음 VOD 정보를 바탕으로 감독명을 추론해주세요.
정확히 알 수 없으면 반드시 UNKNOWN 이라고만 반환하세요.

제목: {vod.get('asset_nm', '')}
분류: {vod.get('ct_cl', '')}
장르: {vod.get('genre', '')} / {vod.get('genre_detail', '')}
제공사: {vod.get('provider', '')}
방영일: {vod.get('release_date', '')}

감독명만 반환 (예: 봉준호 또는 UNKNOWN):"""


def _prompt_smry(vod: dict) -> str:
    director_line = f"\n감독: {vod['director']}" if vod.get('director') else ""
    cast_line     = f"\n주연: {vod['cast_lead']}" if vod.get('cast_lead') else ""
    return f"""다음 VOD 정보를 바탕으로 2~3문장의 한국어 줄거리를 작성해주세요.
정보가 너무 부족해 작성이 불가능하면 반드시 UNKNOWN 이라고만 반환하세요.

제목: {vod.get('asset_nm', '')}
분류: {vod.get('ct_cl', '')}
장르: {vod.get('genre', '')} / {vod.get('genre_detail', '')}{director_line}{cast_line}
방영일: {vod.get('release_date', '')}

2~3문장 한국어 줄거리 (또는 UNKNOWN):"""


# ---------------------------------------------------------------------------
# Claude 호출
# ---------------------------------------------------------------------------

def _call_claude(prompt: str, max_tokens: int) -> str:
    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


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
            raw = _call_claude(_prompt_director(vod), max_tokens=64)
            director = None if raw.upper() == "UNKNOWN" else raw

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE vod
                        SET director         = %s,
                            rag_processed    = TRUE,
                            rag_source       = 'CLAUDE_INFERENCE',
                            rag_processed_at = NOW()
                        WHERE full_asset_id = %s
                    """, (director, vod['full_asset_id']))

            if director:
                success += 1
            else:
                skipped += 1

        except Exception as e:
            failed += 1
            logger.error(f"  [오류] {vod['full_asset_id']} ({vod['asset_nm']}): {e}")

        if i % 50 == 0:
            logger.info(f"  진행: {i}/{len(vods)} (성공:{success}, 스킵:{skipped}, 실패:{failed})")

    logger.info(f"director 처리 완료 — 성공:{success}, UNKNOWN:{skipped}, 오류:{failed}")


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
            raw = _call_claude(_prompt_smry(vod), max_tokens=256)
            smry = None if raw.upper() == "UNKNOWN" else raw

            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE vod
                        SET smry             = %s,
                            rag_processed    = TRUE,
                            rag_source       = 'CLAUDE_GENERATED',
                            rag_processed_at = NOW()
                        WHERE full_asset_id = %s
                    """, (smry, vod['full_asset_id']))

            if smry:
                success += 1
            else:
                skipped += 1

        except Exception as e:
            failed += 1
            logger.error(f"  [오류] {vod['full_asset_id']} ({vod['asset_nm']}): {e}")

        if i % 10 == 0:
            logger.info(f"  진행: {i}/{len(vods)} (성공:{success}, 스킵:{skipped}, 실패:{failed})")

    logger.info(f"smry 처리 완료 — 성공:{success}, UNKNOWN:{skipped}, 오류:{failed}")


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
    if not config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    logger.info("=== 결측치 보완 파이프라인 시작 ===")
    process_missing_directors()
    process_missing_smry()
    print_summary()
    logger.info("=== 완료 ===")
