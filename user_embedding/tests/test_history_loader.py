"""
history_loader.py TDD 테스트
Red → Green → Refactor

테스트 전략: DB 의존성을 unittest.mock으로 격리
실제 DB 연결 없이 순수 로직만 검증
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.history_loader import HistoryLoader, WatchRecord


# ---------------------------------------------------------------------------
# 픽스처: 모의 시청이력 데이터
# ---------------------------------------------------------------------------

def make_record(
    vod_id: str = "VOD001",
    days_ago: int = 5,
    completion_rate: float = 0.9,
    satisfaction: float = 4.0,
    is_rewatch: bool = False,
) -> dict:
    """테스트용 watch_history row 생성 헬퍼"""
    strt_dt = datetime.now() - timedelta(days=days_ago)
    return {
        "vod_id_fk": vod_id,
        "strt_dt": strt_dt,
        "completion_rate": completion_rate,
        "satisfaction": satisfaction,
        "is_rewatch": is_rewatch,
    }


MOCK_ROWS = [
    make_record("VOD001", days_ago=1,  completion_rate=1.0,  satisfaction=5.0, is_rewatch=False),
    make_record("VOD002", days_ago=10, completion_rate=0.5,  satisfaction=3.0, is_rewatch=False),
    make_record("VOD003", days_ago=30, completion_rate=0.8,  satisfaction=4.0, is_rewatch=True),
]


# ---------------------------------------------------------------------------
# WatchRecord 데이터클래스 테스트
# ---------------------------------------------------------------------------

class TestWatchRecord:
    def test_from_dict_정상변환(self):
        """dict → WatchRecord 변환이 올바른지"""
        row = make_record("VOD001", days_ago=3, completion_rate=0.9, satisfaction=4.5)
        record = WatchRecord.from_dict(row)
        assert record.vod_id == "VOD001"
        assert record.completion_rate == pytest.approx(0.9)
        assert record.satisfaction == pytest.approx(4.5)
        assert record.is_rewatch is False

    def test_from_dict_completion_rate_범위(self):
        """completion_rate는 0.0~1.0 범위여야 한다"""
        row = make_record(completion_rate=0.0)
        record = WatchRecord.from_dict(row)
        assert 0.0 <= record.completion_rate <= 1.0

    def test_from_dict_satisfaction_기본값(self):
        """satisfaction이 None이면 0.0으로 처리"""
        row = make_record()
        row["satisfaction"] = None
        record = WatchRecord.from_dict(row)
        assert record.satisfaction == pytest.approx(0.0)

    def test_days_ago_계산(self):
        """strt_dt 기준 경과일 계산이 올바른지"""
        row = make_record(days_ago=7)
        record = WatchRecord.from_dict(row)
        assert 6 <= record.days_ago <= 8  # 부동소수점 오차 허용


# ---------------------------------------------------------------------------
# HistoryLoader 테스트
# ---------------------------------------------------------------------------

class TestHistoryLoader:

    @patch("src.history_loader.get_conn")
    def test_load_정상조회(self, mock_get_conn):
        """정상적인 시청이력 조회 시 WatchRecord 리스트 반환"""
        # DB mock 설정
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("vod_id_fk",), ("strt_dt",), ("completion_rate",),
            ("satisfaction",), ("is_rewatch",),
        ]
        mock_cur.fetchall.return_value = [
            ("VOD001", datetime.now() - timedelta(days=1), 1.0, 5.0, False),
            ("VOD002", datetime.now() - timedelta(days=10), 0.5, 3.0, False),
        ]

        loader = HistoryLoader()
        records = loader.load("USER_HASH_123")

        assert len(records) == 2
        assert records[0].vod_id == "VOD001"
        assert records[1].vod_id == "VOD002"

    @patch("src.history_loader.get_conn")
    def test_load_빈이력(self, mock_get_conn):
        """시청이력이 없는 사용자 → 빈 리스트 반환 (예외 없음)"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("vod_id_fk",), ("strt_dt",), ("completion_rate",),
            ("satisfaction",), ("is_rewatch",),
        ]
        mock_cur.fetchall.return_value = []

        loader = HistoryLoader()
        records = loader.load("UNKNOWN_USER")

        assert records == []

    @patch("src.history_loader.get_conn")
    def test_load_limit_적용(self, mock_get_conn):
        """limit 파라미터가 SQL에 전달되는지"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("vod_id_fk",), ("strt_dt",), ("completion_rate",),
            ("satisfaction",), ("is_rewatch",),
        ]
        mock_cur.fetchall.return_value = []

        loader = HistoryLoader()
        loader.load("USER_HASH_123", limit=50)

        # execute 호출 시 limit 값이 파라미터로 전달됐는지 확인
        call_args = mock_cur.execute.call_args
        assert 50 in call_args[0][1]  # SQL 파라미터 튜플에 50 포함

    @patch("src.history_loader.get_conn")
    def test_load_min_completion_필터(self, mock_get_conn):
        """min_completion 이상인 row만 반환"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("vod_id_fk",), ("strt_dt",), ("completion_rate",),
            ("satisfaction",), ("is_rewatch",),
        ]
        # DB에서는 이미 필터된 결과만 반환한다고 가정 (SQL WHERE 절)
        mock_cur.fetchall.return_value = [
            ("VOD001", datetime.now() - timedelta(days=1), 0.8, 4.0, False),
        ]

        loader = HistoryLoader()
        records = loader.load("USER_HASH_123", min_completion=0.3)

        # min_completion이 SQL 파라미터에 포함됐는지 확인
        call_args = mock_cur.execute.call_args
        assert 0.3 in call_args[0][1]

    def test_load_user_id_빈문자열_예외(self):
        """user_id가 빈 문자열이면 ValueError 발생"""
        loader = HistoryLoader()
        with pytest.raises(ValueError, match="user_id"):
            loader.load("")

    def test_load_user_id_None_예외(self):
        """user_id가 None이면 ValueError 발생"""
        loader = HistoryLoader()
        with pytest.raises(ValueError, match="user_id"):
            loader.load(None)
