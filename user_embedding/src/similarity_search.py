"""
similarity_search.py — user 벡터 기반 유사 VOD 검색

user embedding 벡터와 vod_embedding 테이블의 content_vector를
pgvector cosine 유사도(<=>)로 비교하여 상위 N개 VOD를 반환한다.

pgvector HNSW 인덱스(vector_cosine_ops) 활용 → 빠른 ANN 검색

사용 예:
    from src.similarity_search import SimilaritySearch

    results = searcher.search(
        user_vec,
        top_k=20,
        ct_cl_filter=["영화", "TV드라마"],
        exclude_ratings=["청소년관람불가"],
    )
    for r in results:
        print(r.asset_nm, r.similarity)
"""
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from db import get_conn

logger = logging.getLogger(__name__)

_EMBEDDING_TYPE = "METADATA"
_EMBEDDING_DIM  = 384


# ---------------------------------------------------------------------------
# 결과 모델
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """
    유사도 검색 결과 단건

    Attributes:
        vod_id:     full_asset_id
        asset_nm:   VOD 제목
        ct_cl:      콘텐츠 유형 (영화/TV드라마 등)
        genre:      장르
        rating:     시청등급
        similarity: cosine 유사도 (0.0 ~ 1.0)
    """
    vod_id:     str
    asset_nm:   str
    ct_cl:      str
    genre:      str
    rating:     Optional[str]
    similarity: float

    @classmethod
    def from_row(cls, row: tuple) -> "SearchResult":
        """DB fetchall row tuple → SearchResult"""
        vod_id, asset_nm, ct_cl, genre, rating, similarity = row
        return cls(
            vod_id=vod_id,
            asset_nm=asset_nm,
            ct_cl=ct_cl,
            genre=genre,
            rating=rating,
            similarity=float(similarity),
        )


# ---------------------------------------------------------------------------
# SimilaritySearch
# ---------------------------------------------------------------------------

class SimilaritySearch:
    """
    user embedding 벡터로 유사 VOD를 검색한다.

    Args:
        embedding_dim: 임베딩 차원 (기본 384)
        default_top_k: 기본 반환 건수 (기본 20)
    """

    def __init__(
        self,
        embedding_dim: int = _EMBEDDING_DIM,
        default_top_k: int = 20,
    ) -> None:
        self.embedding_dim = embedding_dim
        self.default_top_k = default_top_k

    def search(
        self,
        user_vec: Optional[np.ndarray],
        top_k: Optional[int] = None,
        ct_cl_filter: Optional[list[str]] = None,
        exclude_ratings: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """
        user 벡터와 cosine 유사도가 높은 VOD를 반환한다.

        Args:
            user_vec:        UserEmbedder.build()가 반환한 384d numpy 벡터
            top_k:           반환할 최대 건수 (기본 default_top_k)
            ct_cl_filter:    포함할 ct_cl 목록. None이면 전체.
                             예) ["영화", "TV드라마"]
            exclude_ratings: 제외할 등급 목록. None이면 제외 없음.
                             예) ["청소년관람불가"]

        Returns:
            SearchResult 리스트 (similarity 내림차순)

        Raises:
            ValueError: user_vec가 None이거나 차원이 맞지 않는 경우
        """
        if user_vec is None:
            raise ValueError("user_vec는 None일 수 없습니다.")
        if not isinstance(user_vec, np.ndarray) or user_vec.shape != (self.embedding_dim,):
            raise ValueError(
                f"user_vec 차원이 올바르지 않습니다. "
                f"기대: ({self.embedding_dim},), 실제: {getattr(user_vec, 'shape', type(user_vec))}"
            )

        _top_k = top_k if top_k is not None else self.default_top_k

        # pgvector 입력 형식: "[0.1,0.2,...]"
        vec_str = "[" + ",".join(f"{x:.8f}" for x in user_vec.tolist()) + "]"

        # 동적 WHERE 절 구성
        conditions = ["v.is_active = TRUE", "ve.embedding_type = %s"]
        params: list = [_EMBEDDING_TYPE]

        if ct_cl_filter:
            conditions.append("v.ct_cl = ANY(%s)")
            params.append(ct_cl_filter)

        if exclude_ratings:
            conditions.append("(v.rating IS NULL OR v.rating != ALL(%s))")
            params.append(exclude_ratings)

        where_clause = " AND ".join(conditions)
        params.extend([vec_str, vec_str, _top_k])

        sql = f"""
            SELECT DISTINCT ON (v.asset_nm)
                v.full_asset_id,
                v.asset_nm,
                v.ct_cl,
                v.genre,
                v.rating,
                ROUND((1 - (ve.content_vector <=> %s::vector))::numeric, 4) AS similarity
            FROM vod_embedding ve
            JOIN vod v ON ve.vod_id_fk = v.full_asset_id
            WHERE {where_clause}
            ORDER BY v.asset_nm,
                     ve.content_vector <=> %s::vector
            LIMIT %s
        """

        # DISTINCT ON + 유사도 내림차순 정렬을 위해 서브쿼리로 감쌈
        outer_sql = f"""
            SELECT * FROM ({sql}) sub
            ORDER BY similarity DESC
        """

        logger.debug(
            "유사도 검색 — top_k=%d, ct_cl=%s, exclude_ratings=%s",
            _top_k, ct_cl_filter, exclude_ratings,
        )

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(outer_sql, params)
                rows = cur.fetchall()

        results = [SearchResult.from_row(row) for row in rows]
        logger.debug("검색 완료: %d건 반환", len(results))
        return results
