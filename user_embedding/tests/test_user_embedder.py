"""
user_embedder.py TDD 테스트
Red → Green → Refactor

테스트 전략: DB 의존성 mock, numpy 연산은 실제 실행
"""
import math
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.history_loader import WatchRecord
from src.user_embedder import UserEmbedder


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

def make_record(
    vod_id: str,
    days_ago: float = 1.0,
    completion_rate: float = 1.0,
    satisfaction: float = 5.0,
    is_rewatch: bool = False,
) -> WatchRecord:
    strt_dt = datetime.now() - timedelta(days=days_ago)
    return WatchRecord(
        vod_id=vod_id,
        strt_dt=strt_dt,
        completion_rate=completion_rate,
        satisfaction=satisfaction,
        is_rewatch=is_rewatch,
    )


def make_vector(seed: int = 0, dim: int = 384) -> np.ndarray:
    """재현 가능한 단위 벡터 생성"""
    rng = np.random.default_rng(seed)
    v = rng.random(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# 가중치 계산 테스트
# ---------------------------------------------------------------------------

class TestWeightCalculation:

    def test_recency_decay_최근일수록_높다(self):
        """최근 시청일수록 recency_decay 가중치가 높아야 한다"""
        embedder = UserEmbedder()
        recent  = embedder._recency_decay(days_ago=1)
        old     = embedder._recency_decay(days_ago=30)
        assert recent > old

    def test_recency_decay_0일은_1에_가깝다(self):
        """당일 시청은 decay ≈ 1.0"""
        embedder = UserEmbedder()
        assert embedder._recency_decay(days_ago=0) == pytest.approx(1.0, abs=1e-3)

    def test_recency_decay_음수_일수_예외(self):
        """음수 days_ago는 ValueError"""
        embedder = UserEmbedder()
        with pytest.raises(ValueError):
            embedder._recency_decay(days_ago=-1)

    def test_record_weight_재시청_가중치_높다(self):
        """is_rewatch=True면 동일 조건 대비 가중치가 높아야 한다"""
        embedder = UserEmbedder()
        normal  = make_record("V1", is_rewatch=False)
        rewatch = make_record("V2", is_rewatch=True)
        assert embedder._record_weight(rewatch) > embedder._record_weight(normal)

    def test_record_weight_completion_높을수록_높다(self):
        """completion_rate 높을수록 가중치 증가"""
        embedder = UserEmbedder()
        low  = make_record("V1", completion_rate=0.2)
        high = make_record("V2", completion_rate=1.0)
        assert embedder._record_weight(high) > embedder._record_weight(low)

    def test_record_weight_satisfaction_높을수록_높다(self):
        """satisfaction 높을수록 가중치 증가"""
        embedder = UserEmbedder()
        low  = make_record("V1", satisfaction=1.0)
        high = make_record("V2", satisfaction=5.0)
        assert embedder._record_weight(high) > embedder._record_weight(low)

    def test_record_weight_항상_양수(self):
        """completion_rate > 0 이면 가중치는 양수여야 한다"""
        embedder = UserEmbedder()
        record = make_record("V1", completion_rate=0.1, satisfaction=0.0)
        assert embedder._record_weight(record) > 0

    def test_record_weight_completion_zero_이면_zero(self):
        """completion_rate=0.0 이면 가중치=0 (안 본 콘텐츠는 제외)"""
        embedder = UserEmbedder()
        record = make_record("V1", completion_rate=0.0, satisfaction=5.0)
        assert embedder._record_weight(record) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 벡터 합성 테스트
# ---------------------------------------------------------------------------

class TestVectorAggregation:

    @patch("src.user_embedder.get_conn")
    def test_build_정상반환(self, mock_get_conn):
        """정상 시청이력 → 384d numpy 배열 반환"""
        vec1 = make_vector(seed=1)
        vec2 = make_vector(seed=2)

        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = [
            ("VOD001", "[" + ",".join(str(x) for x in vec1.tolist()) + "]"),
            ("VOD002", "[" + ",".join(str(x) for x in vec2.tolist()) + "]"),
        ]

        records = [
            make_record("VOD001", days_ago=1),
            make_record("VOD002", days_ago=10),
        ]

        embedder = UserEmbedder()
        result = embedder.build(records)

        assert isinstance(result, np.ndarray)
        assert result.shape == (384,)

    @patch("src.user_embedder.get_conn")
    def test_build_단위벡터_반환(self, mock_get_conn):
        """결과 벡터는 L2 정규화된 단위벡터여야 한다 (magnitude ≈ 1.0)"""
        vec1 = make_vector(seed=1)

        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = [
            ("VOD001", "[" + ",".join(str(x) for x in vec1.tolist()) + "]"),
        ]

        records = [make_record("VOD001")]
        embedder = UserEmbedder()
        result = embedder.build(records)

        magnitude = float(np.linalg.norm(result))
        assert magnitude == pytest.approx(1.0, abs=1e-5)

    def test_build_빈이력_예외(self):
        """시청이력 없으면 ValueError"""
        embedder = UserEmbedder()
        with pytest.raises(ValueError, match="시청이력"):
            embedder.build([])

    @patch("src.user_embedder.get_conn")
    def test_build_임베딩없는_vod_스킵(self, mock_get_conn):
        """vod_embedding에 없는 VOD는 무시하고 나머지로 벡터 생성"""
        vec1 = make_vector(seed=1)

        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # VOD001만 임베딩 존재, VOD002는 없음
        mock_cur.fetchall.return_value = [
            ("VOD001", "[" + ",".join(str(x) for x in vec1.tolist()) + "]"),
        ]

        records = [
            make_record("VOD001"),
            make_record("VOD002"),
        ]
        embedder = UserEmbedder()
        result = embedder.build(records)  # 예외 없이 VOD001 기반 벡터 반환

        assert result.shape == (384,)

    @patch("src.user_embedder.get_conn")
    def test_build_전부_임베딩없으면_예외(self, mock_get_conn):
        """모든 VOD 임베딩이 없으면 ValueError"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = []  # 아무것도 없음

        records = [make_record("VOD_UNKNOWN")]
        embedder = UserEmbedder()
        with pytest.raises(ValueError, match="임베딩"):
            embedder.build(records)

    @patch("src.user_embedder.get_conn")
    def test_build_가중치_실제_반영(self, mock_get_conn):
        """최근·고만족 시청 VOD 방향으로 결과 벡터가 편향되어야 한다"""
        # vec1: 최근(1일), 고만족(5.0) → 높은 가중치
        # vec2: 오래됨(60일), 저만족(1.0) → 낮은 가중치
        vec1 = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        vec2 = np.array([0.0, 1.0] + [0.0] * 382, dtype=np.float32)

        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = [
            ("VOD001", "[" + ",".join(str(x) for x in vec1.tolist()) + "]"),
            ("VOD002", "[" + ",".join(str(x) for x in vec2.tolist()) + "]"),
        ]

        records = [
            make_record("VOD001", days_ago=1,  satisfaction=5.0, completion_rate=1.0),
            make_record("VOD002", days_ago=60, satisfaction=1.0, completion_rate=0.1),
        ]
        embedder = UserEmbedder()
        result = embedder.build(records)

        # 결과 벡터의 첫 번째 차원(vec1 방향) 값이 두 번째(vec2 방향)보다 커야 함
        assert result[0] > result[1]
