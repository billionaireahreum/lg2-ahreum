"""
VOD 콘텐츠 임베딩 재생성 파이프라인 (시리즈 단위, v2)

기존 02_generate_embeddings.py 대비 변경사항:
  - 시리즈 단위 처리: normalized_title + ct_cl 기준으로 그룹핑
  - 임베딩 1회 연산 → 시리즈 내 전체 row에 동일 벡터 복사 (중복 연산 방지)
  - 입력 텍스트에 cast_guest, release_date 추가

입력 텍스트 구성:
  제목 / 유형 / 장르 / 세부장르 / 감독: xxx / 주연: xxx / 조연: xxx / 줄거리 / 개봉연도

모델: paraphrase-multilingual-MiniLM-L12-v2 (384d, 한국어 지원)
저장: vod_embedding 테이블 (ON CONFLICT DO UPDATE — 기존 임베딩 덮어씀)

실행:
  cd user_embedding/pipeline
  python generate_embeddings.py

멱등성: 재실행해도 안전 (ON CONFLICT DO UPDATE)
"""
import logging
import re
import sys
from collections import defaultdict

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
# 제목 정규화 (03번 파이프라인과 동일 로직)
# ---------------------------------------------------------------------------

def normalize_title(title: str) -> str:
    """
    시리즈 식별을 위한 제목 정규화.
    에피소드 번호·화질·자막 표기 등을 제거해 동일 콘텐츠로 묶는다.

    예) '겨울왕국 [4K]', '겨울왕국 (더빙)', '겨울왕국 1회' → '겨울왕국'
    """
    if not title:
        return ''
    # 괄호류 태그 제거: [자막], (더빙), 【HD】, （4K） 등
    t = re.sub(r'[\(\[【（][^\)\]】）]*[\)\]】）]', '', title)
    # 에피소드/시즌 표기 제거: 1회, 시즌2, 시즌 2, EP1 등
    t = re.sub(r'\s*\d+회\b', '', t)
    t = re.sub(r'\s*시즌\s*\d+', '', t)
    t = re.sub(r'\s*EP\d+', '', t, flags=re.IGNORECASE)
    return t.strip()


# ---------------------------------------------------------------------------
# 임베딩 입력 텍스트 구성
# ---------------------------------------------------------------------------

def build_vod_text(vod: dict) -> str:
    """
    VOD 메타데이터를 임베딩용 단일 텍스트로 변환.

    포함 필드: 제목 / 유형 / 장르 / 세부장르 / 감독 / 주연 / 조연 / 줄거리 / 개봉연도
    rating은 필터링 전용이므로 임베딩 텍스트에서 제외.
    """
    parts: list[str] = [
        vod.get('asset_nm', ''),
        vod.get('ct_cl', ''),
        vod.get('genre', ''),
        vod.get('genre_detail', ''),
    ]
    if vod.get('director'):
        parts.append(f"감독: {vod['director']}")
    if vod.get('cast_lead'):
        parts.append(f"주연: {vod['cast_lead']}")
    if vod.get('cast_guest'):
        parts.append(f"조연: {vod['cast_guest']}")
    if vod.get('smry'):
        parts.append(vod['smry'])
    if vod.get('release_date'):
        # 연도만 추출해서 추가 (날짜 전체는 노이즈)
        year = str(vod['release_date'])[:4]
        parts.append(year)
    return ' '.join(filter(None, parts))


# ---------------------------------------------------------------------------
# 대표 row 선택 (시리즈 내 메타데이터 완성도가 높은 row 우선)
# ---------------------------------------------------------------------------

def _completeness_score(vod: dict) -> int:
    """채워진 핵심 필드 수를 점수로 반환 (높을수록 좋음)"""
    fields = ['director', 'cast_lead', 'cast_guest', 'smry', 'release_date']
    return sum(1 for f in fields if vod.get(f))


def pick_representative(vods: list[dict]) -> dict:
    """시리즈 내 대표 row 선택: 메타데이터 완성도 기준"""
    return max(vods, key=_completeness_score)


# ---------------------------------------------------------------------------
# 전체 VOD 조회
# ---------------------------------------------------------------------------

def fetch_all_vods() -> list[dict]:
    """
    임베딩 생성에 필요한 전체 활성 VOD 조회.
    is_active=TRUE 조건만 적용 (ct_cl 제한 없음 — 전 장르 임베딩).
    """
    logger.info("VOD 메타데이터 로딩 중...")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    full_asset_id,
                    asset_nm,
                    ct_cl,
                    genre,
                    genre_detail,
                    director,
                    cast_lead,
                    cast_guest,
                    smry,
                    release_date
                FROM vod
                WHERE is_active = TRUE
                ORDER BY full_asset_id
            """)
            rows = fetch_all_as_dict(cur)
    logger.info(f"  전체 활성 VOD: {len(rows):,}건 로드 완료")
    return rows


# ---------------------------------------------------------------------------
# 시리즈 단위 그룹핑
# ---------------------------------------------------------------------------

def group_by_series(vods: list[dict]) -> dict[tuple, list[dict]]:
    """
    (normalized_title, ct_cl) 기준으로 시리즈 그룹핑.
    반환: {(normalized_title, ct_cl): [vod, vod, ...], ...}
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for vod in vods:
        key = (normalize_title(vod['asset_nm']), vod['ct_cl'])
        groups[key].append(vod)
    return groups


# ---------------------------------------------------------------------------
# 배치 저장
# ---------------------------------------------------------------------------

def save_batch(rows: list[tuple]) -> None:
    """
    vod_embedding 테이블에 임베딩 일괄 저장.
    ON CONFLICT DO UPDATE → 기존 임베딩 덮어씀 (재생성 안전).

    rows: [(vod_id_fk, embedding_type, dim, model, magnitude, vec_str), ...]
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

def run() -> None:
    logger.info("=== VOD 콘텐츠 임베딩 재생성 파이프라인 시작 (시리즈 단위 v2) ===")

    # 1. 모델 로드
    logger.info(f"임베딩 모델 로드: {config.EMBEDDING_MODEL}")
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    # 2. 전체 VOD 조회 및 시리즈 그룹핑
    all_vods = fetch_all_vods()
    series_groups = group_by_series(all_vods)
    total_series = len(series_groups)
    total_rows   = len(all_vods)
    logger.info(f"  시리즈 그룹 수: {total_series:,}개 (row {total_rows:,}건 → {total_series:,}번 연산)")

    # 3. 시리즈 단위 임베딩 연산 + 저장
    series_list = list(series_groups.items())
    done_series = 0
    done_rows   = 0
    pending_rows: list[tuple] = []  # 저장 대기 버퍼

    for (norm_title, ct_cl), group_vods in series_list:
        # 대표 row 선택 → 임베딩 텍스트 구성
        rep = pick_representative(group_vods)
        text = build_vod_text(rep)

        # 임베딩 연산 (1건)
        vec: np.ndarray = model.encode(
            [text],
            normalize_embeddings=True,  # L2 정규화 → cosine = dot product
            show_progress_bar=False,
        )[0]
        magnitude = float(np.linalg.norm(vec))
        vec_str = "[" + ",".join(f"{x:.8f}" for x in vec.tolist()) + "]"

        # 시리즈 내 전체 row에 동일 벡터 부여
        for vod in group_vods:
            pending_rows.append((
                vod['full_asset_id'],
                config.EMBEDDING_TYPE,
                config.EMBEDDING_DIM,
                config.EMBEDDING_MODEL,
                magnitude,
                vec_str,
            ))

        done_series += 1
        done_rows   += len(group_vods)

        # BATCH_SIZE(row 수 기준)마다 저장
        if len(pending_rows) >= config.BATCH_SIZE:
            save_batch(pending_rows)
            pending_rows = []
            logger.info(
                f"  [{done_series:,}/{total_series:,}] 시리즈 {done_series/total_series*100:.1f}%"
                f" | row {done_rows:,}/{total_rows:,}"
            )

    # 잔여 저장
    if pending_rows:
        save_batch(pending_rows)
        logger.info(
            f"  [{done_series:,}/{total_series:,}] 시리즈 {done_series/total_series*100:.1f}%"
            f" | row {done_rows:,}/{total_rows:,}"
        )

    logger.info(f"임베딩 생성 완료: 시리즈 {done_series:,}개 / row {done_rows:,}건")


# ---------------------------------------------------------------------------
# 검증 출력
# ---------------------------------------------------------------------------

def print_summary() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM vod WHERE is_active = TRUE)       AS total_vod,
                    (SELECT COUNT(*) FROM vod_embedding
                     WHERE embedding_type = %s)                              AS embedded,
                    (SELECT ROUND(AVG(vector_magnitude)::NUMERIC, 6)
                     FROM vod_embedding WHERE embedding_type = %s)           AS avg_magnitude
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
    run()
    print_summary()
    logger.info("=== 완료 ===")
