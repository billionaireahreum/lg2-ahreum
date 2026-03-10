"""
user_embedder.py — 사용자 임베딩 생성

사용자의 시청이력(WatchRecord 리스트)을 받아
각 VOD의 content_vector를 가중 평균하여 384d user 벡터를 생성한다.

가중치 공식:
    weight = completion_rate × (1 + satisfaction / 5) × recency_decay × rewatch_bonus
    recency_decay = exp(-days_ago / halflife)   # 기본 반감기 30일
    rewatch_bonus = 1.2 if is_rewatch else 1.0

결과 벡터는 L2 정규화 (magnitude = 1.0) → vod_embedding과 cosine 비교 가능

사용 예:
    from src.history_loader import HistoryLoader
    from src.user_embedder import UserEmbedder

    records = HistoryLoader().load("sha2_hash_값")
    user_vec = UserEmbedder().build(records)
"""
import logging
import math
import sys
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from db import get_conn

from src.history_loader import WatchRecord

logger = logging.getLogger(__name__)

_EMBEDDING_TYPE = "METADATA"
_REWATCH_BONUS  = 1.2


class UserEmbedder:
    """
    시청이력 기반 user embedding 생성기.

    Args:
        halflife_days: recency_decay 반감기 (일). 기본 30일.
        embedding_dim: 임베딩 차원. 기본 384.
    """

    def __init__(
        self,
        halflife_days: float = 30.0,
        embedding_dim: int = 384,
    ) -> None:
        self.halflife_days = halflife_days
        self.embedding_dim = embedding_dim

    # -----------------------------------------------------------------------
    # 가중치 계산
    # -----------------------------------------------------------------------

    def _recency_decay(self, days_ago: float) -> float:
        """
        시청 경과일 기반 지수 감쇠 가중치.
        days_ago=0 → 1.0, days_ago=halflife → 0.5

        Raises:
            ValueError: days_ago < 0
        """
        if days_ago < 0:
            raise ValueError(f"days_ago는 0 이상이어야 합니다. 입력값: {days_ago}")
        return math.exp(-days_ago * math.log(2) / self.halflife_days)

    def _record_weight(self, record: WatchRecord) -> float:
        """
        시청 레코드 1건의 가중치 계산.

        completion_rate × (1 + satisfaction/5) × recency_decay × rewatch_bonus

        반환값은 항상 양수 (completion_rate=0, satisfaction=0 이어도 recency×bonus > 0).
        """
        recency = self._recency_decay(record.days_ago)
        bonus   = _REWATCH_BONUS if record.is_rewatch else 1.0
        weight  = record.completion_rate * (1 + record.satisfaction / 5) * recency * bonus
        # completion_rate=0이면 가중치=0이 되어 해당 VOD가 무시됨
        # 최소 recency 성분만이라도 살리려면 아래처럼 max 처리 가능하나,
        # 거의 안 본 콘텐츠(0%)는 관심 없다고 판단해 그대로 0 허용
        return weight

    # -----------------------------------------------------------------------
    # VOD 임베딩 일괄 조회
    # -----------------------------------------------------------------------

    def _fetch_vectors(
        self, vod_ids: list[str]
    ) -> dict[str, np.ndarray]:
        """
        vod_embedding 테이블에서 vod_id 목록의 content_vector를 조회.
        반환: {vod_id: np.ndarray(384,), ...}  — 없는 vod_id는 포함 안 됨
        """
        if not vod_ids:
            return {}

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT vod_id_fk,
                           content_vector::text
                    FROM vod_embedding
                    WHERE vod_id_fk    = ANY(%s)
                      AND embedding_type = %s
                    """,
                    (vod_ids, _EMBEDDING_TYPE),
                )
                rows = cur.fetchall()

        result: dict[str, np.ndarray] = {}
        for vod_id, vec_text in rows:
            # pgvector text 형식 "[0.1,0.2,...]" → numpy 배열
            values = [float(x) for x in vec_text.strip("[]").split(",")]
            result[vod_id] = np.array(values, dtype=np.float32)

        logger.debug("벡터 조회: 요청 %d건 / 반환 %d건", len(vod_ids), len(result))
        return result

    # -----------------------------------------------------------------------
    # user 벡터 생성 (메인)
    # -----------------------------------------------------------------------

    def build(self, records: list[WatchRecord]) -> np.ndarray:
        """
        시청이력 리스트 → 384d user embedding 벡터 (L2 정규화).

        Args:
            records: HistoryLoader.load()가 반환한 WatchRecord 리스트

        Returns:
            np.ndarray shape=(384,), dtype=float32, magnitude=1.0

        Raises:
            ValueError: records가 비어있는 경우
            ValueError: 모든 VOD의 임베딩이 존재하지 않는 경우
        """
        if not records:
            raise ValueError("시청이력이 없습니다. records가 비어 있습니다.")

        # 1. VOD 임베딩 일괄 조회
        vod_ids = [r.vod_id for r in records]
        vec_map = self._fetch_vectors(vod_ids)

        if not vec_map:
            raise ValueError(
                f"임베딩이 존재하는 VOD가 없습니다. "
                f"vod_ids={vod_ids[:5]}{'...' if len(vod_ids) > 5 else ''}"
            )

        # 2. 가중 평균 계산
        weighted_sum = np.zeros(self.embedding_dim, dtype=np.float64)
        total_weight = 0.0
        skipped      = 0

        for record in records:
            vec = vec_map.get(record.vod_id)
            if vec is None:
                skipped += 1
                continue

            weight        = self._record_weight(record)
            weighted_sum += weight * vec.astype(np.float64)
            total_weight += weight

        if skipped:
            logger.debug("임베딩 없어 스킵된 VOD: %d건", skipped)

        if total_weight == 0:
            raise ValueError(
                "모든 레코드의 가중치 합이 0입니다. "
                "(completion_rate=0인 레코드만 존재하거나 임베딩이 없는 경우)"
            )

        # 3. L2 정규화 → magnitude = 1.0
        user_vec = (weighted_sum / total_weight).astype(np.float32)
        norm     = np.linalg.norm(user_vec)
        if norm > 0:
            user_vec = user_vec / norm

        logger.debug(
            "user 벡터 생성 완료 — 사용 VOD: %d건, magnitude: %.6f",
            len(vec_map) - skipped,
            float(np.linalg.norm(user_vec)),
        )
        return user_vec
