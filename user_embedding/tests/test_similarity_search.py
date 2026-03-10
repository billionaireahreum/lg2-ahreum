"""
similarity_search.py TDD 테스트
Red → Green → Refactor

테스트 전략: DB 의존성 mock, 결과 정렬·필터 로직 검증
"""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.similarity_search import SimilaritySearch, SearchResult


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

def make_user_vec(dim: int = 384) -> np.ndarray:
    rng = np.random.default_rng(42)
    v = rng.random(dim).astype(np.float32)
    return v / np.linalg.norm(v)


MOCK_ROWS = [
    ("VOD001", "액션영화A", "영화", "액션/어드벤쳐", "15세이상관람가", 0.92),
    ("VOD002", "액션영화B", "영화", "액션/어드벤쳐", "청소년관람불가", 0.88),
    ("VOD003", "드라마A",   "TV드라마", "멜로/로맨스", "15세이상관람가", 0.75),
    ("VOD004", "키즈A",     "키즈",   "애니메이션",   "전체관람가",    0.70),
]


# ---------------------------------------------------------------------------
# SearchResult 테스트
# ---------------------------------------------------------------------------

class TestSearchResult:
    def test_from_row_정상변환(self):
        row = ("VOD001", "액션영화A", "영화", "액션/어드벤쳐", "15세이상관람가", 0.92)
        result = SearchResult.from_row(row)
        assert result.vod_id    == "VOD001"
        assert result.asset_nm  == "액션영화A"
        assert result.ct_cl     == "영화"
        assert result.genre     == "액션/어드벤쳐"
        assert result.rating    == "15세이상관람가"
        assert result.similarity == pytest.approx(0.92)

    def test_similarity_범위(self):
        """similarity는 0~1 사이여야 한다"""
        row = ("VOD001", "영화A", "영화", "액션", "전체관람가", 0.85)
        result = SearchResult.from_row(row)
        assert 0.0 <= result.similarity <= 1.0


# ---------------------------------------------------------------------------
# SimilaritySearch 테스트
# ---------------------------------------------------------------------------

class TestSimilaritySearch:

    @patch("src.similarity_search.get_conn")
    def test_search_정상반환(self, mock_get_conn):
        """정상 user_vec → SearchResult 리스트 반환"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = MOCK_ROWS[:2]

        searcher = SimilaritySearch()
        results  = searcher.search(make_user_vec())

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].vod_id == "VOD001"

    @patch("src.similarity_search.get_conn")
    def test_search_유사도_내림차순(self, mock_get_conn):
        """결과는 similarity 내림차순 정렬이어야 한다"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = MOCK_ROWS  # 0.92, 0.88, 0.75, 0.70 순

        searcher = SimilaritySearch()
        results  = searcher.search(make_user_vec(), top_k=10)

        sims = [r.similarity for r in results]
        assert sims == sorted(sims, reverse=True)

    @patch("src.similarity_search.get_conn")
    def test_search_top_k_적용(self, mock_get_conn):
        """top_k 개수만큼만 반환"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = MOCK_ROWS[:2]

        searcher = SimilaritySearch()
        searcher.search(make_user_vec(), top_k=2)

        # SQL 파라미터에 top_k 값이 포함됐는지 확인
        call_args = mock_cur.execute.call_args
        assert 2 in call_args[0][1]

    @patch("src.similarity_search.get_conn")
    def test_search_ct_cl_필터(self, mock_get_conn):
        """ct_cl 필터가 SQL 파라미터에 포함되는지"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        searcher = SimilaritySearch()
        searcher.search(make_user_vec(), ct_cl_filter=["영화", "TV드라마"])

        call_args = mock_cur.execute.call_args
        params    = call_args[0][1]
        assert ["영화", "TV드라마"] in params

    @patch("src.similarity_search.get_conn")
    def test_search_rating_필터(self, mock_get_conn):
        """exclude_ratings 필터가 SQL 파라미터에 포함되는지"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        searcher = SimilaritySearch()
        searcher.search(make_user_vec(), exclude_ratings=["청소년관람불가"])

        call_args = mock_cur.execute.call_args
        params    = call_args[0][1]
        assert ["청소년관람불가"] in params

    @patch("src.similarity_search.get_conn")
    def test_search_결과없으면_빈리스트(self, mock_get_conn):
        """유사한 콘텐츠 없으면 빈 리스트 반환 (예외 없음)"""
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        searcher = SimilaritySearch()
        results  = searcher.search(make_user_vec())

        assert results == []

    def test_search_잘못된벡터_차원_예외(self):
        """384d가 아닌 벡터 입력 시 ValueError"""
        searcher = SimilaritySearch()
        wrong_vec = np.zeros(128, dtype=np.float32)
        with pytest.raises(ValueError, match="차원"):
            searcher.search(wrong_vec)

    def test_search_None_벡터_예외(self):
        """None 벡터 입력 시 ValueError"""
        searcher = SimilaritySearch()
        with pytest.raises(ValueError):
            searcher.search(None)
