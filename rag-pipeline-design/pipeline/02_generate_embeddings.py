"""
VOD 텍스트 임베딩 생성 + pgvector 저장 파이프라인

모델: paraphrase-multilingual-MiniLM-L12-v2 (384d, 한국어 지원)
입력: asset_nm + genre + genre_detail + ct_cl + director + cast_lead + smry
출력: vod_embedding 테이블 (content_vector 컬럼)

실행:
  python pipeline/02_generate_embeddings.py

멱등성: vod_embedding에 없는 VOD만 처리, ON CONFLICT DO UPDATE
"""
import logging

import numpy as np
import psycopg2.extras
from sentence_transformers import SentenceTransformer

import config
from db import fetch_all_as_dict, get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 텍스트 구성
# ---------------------------------------------------------------------------

def build_vod_text(vod: dict) -> str:
    """VOD 메타데이터를 임베딩용 단일 텍스트로 변환"""
    parts = [
        vod.get('asset_nm', ''),
        vod.get('ct_cl', ''),
        vod.get('genre', ''),
        vod.get('genre_detail', ''),
    ]
    if vod.get('director'):
        parts.append(f"감독: {vod['director']}")
    if vod.get('cast_lead'):
        parts.append(f"주연: {vod['cast_lead']}")
    if vod.get('smry'):
        parts.append(vod['smry'])
    return ' '.join(filter(None, parts))


# ---------------------------------------------------------------------------
# VOD 조회
# ---------------------------------------------------------------------------

def fetch_unembedded_vods() -> list[dict]:
    """아직 METADATA 임베딩이 없는 VOD 조회"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    v.full_asset_id, v.asset_nm, v.ct_cl,
                    v.genre, v.genre_detail,
                    v.director, v.cast_lead, v.smry
                FROM vod v
                LEFT JOIN vod_embedding ve
                    ON v.full_asset_id = ve.vod_id_fk
                    AND ve.embedding_type = %s
                WHERE ve.vod_id_fk IS NULL
                  AND v.is_active = TRUE
                ORDER BY v.full_asset_id
            """, (config.EMBEDDING_TYPE,))
            return fetch_all_as_dict(cur)


# ---------------------------------------------------------------------------
# 배치 저장
# ---------------------------------------------------------------------------

def save_batch(rows: list[tuple]):
    """
    rows: [(vod_id_fk, embedding_type, dim, model, magnitude, vector_list), ...]
    vector_list는 Python list[float] → pgvector가 '[a,b,c,...]' 문자열로 받음
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO vod_embedding
                    (vod_id_fk, embedding_type, embedding_dimension,
                     model_version, vector_magnitude, content_vector)
                VALUES %s
                ON CONFLICT (vod_id_fk, embedding_type) DO UPDATE
                    SET content_vector   = EXCLUDED.content_vector,
                        vector_magnitude = EXCLUDED.vector_magnitude,
                        model_version    = EXCLUDED.model_version,
                        updated_at       = NOW()
                """,
                rows,
                template="(%s, %s, %s, %s, %s, %s::vector)",
            )


# ---------------------------------------------------------------------------
# 메인 파이프라인
# ---------------------------------------------------------------------------

def run():
    logger.info(f"임베딩 모델 로드: {config.EMBEDDING_MODEL}")
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    vods = fetch_unembedded_vods()
    total = len(vods)
    if total == 0:
        logger.info("임베딩 처리할 대상 없음 (모두 완료됨)")
        return

    logger.info(f"임베딩 생성 대상: {total:,}건 / 배치 크기: {config.BATCH_SIZE}")

    done = 0
    for batch_start in range(0, total, config.BATCH_SIZE):
        batch = vods[batch_start: batch_start + config.BATCH_SIZE]
        texts = [build_vod_text(v) for v in batch]

        # L2 정규화 → cosine similarity = dot product 로 계산 가능 (pgvector 최적화)
        vectors: np.ndarray = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        rows = []
        for vod, vec in zip(batch, vectors):
            magnitude = float(np.linalg.norm(vec))
            # pgvector는 '[a, b, c, ...]' 형식 문자열 또는 list 허용
            vec_str = "[" + ",".join(f"{x:.8f}" for x in vec.tolist()) + "]"
            rows.append((
                vod['full_asset_id'],
                config.EMBEDDING_TYPE,
                config.EMBEDDING_DIM,
                config.EMBEDDING_MODEL,
                magnitude,
                vec_str,
            ))

        save_batch(rows)
        done += len(batch)
        logger.info(f"  저장 완료: {done:,}/{total:,} ({done/total*100:.1f}%)")

    logger.info(f"임베딩 생성 완료: {done:,}건")


# ---------------------------------------------------------------------------
# 검증 출력
# ---------------------------------------------------------------------------

def print_summary():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM vod WHERE is_active = TRUE)    AS total_vod,
                    (SELECT COUNT(*) FROM vod_embedding
                     WHERE embedding_type = %s)                           AS embedded,
                    (SELECT ROUND(AVG(vector_magnitude)::NUMERIC, 6)
                     FROM vod_embedding WHERE embedding_type = %s)        AS avg_magnitude
            """, (config.EMBEDDING_TYPE, config.EMBEDDING_TYPE))
            row = cur.fetchone()

    total_vod, embedded, avg_mag = row
    pct = embedded / total_vod * 100 if total_vod else 0
    logger.info("=== 임베딩 현황 ===")
    logger.info(f"  전체 VOD       : {total_vod:,}개")
    logger.info(f"  임베딩 완료    : {embedded:,}개 ({pct:.1f}%)")
    logger.info(f"  평균 magnitude : {avg_mag}")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("=== VOD 임베딩 생성 파이프라인 시작 ===")
    run()
    print_summary()
    logger.info("=== 완료 ===")
