"""
history_loader.py — 사용자 시청이력 로드

watch_history 테이블에서 특정 사용자의 시청 기록을 조회하여
WatchRecord 리스트로 반환한다.

사용 예:
    loader = HistoryLoader()
    records = loader.load("sha2_hash_값", limit=100, min_completion=0.3)
"""
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# pipeline/db.py 공유 사용 (상위 경로 추가)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from db import get_conn, fetch_all_as_dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class WatchRecord:
    """
    시청이력 단건 레코드

    Attributes:
        vod_id:          VOD full_asset_id
        strt_dt:         시청 시작 일시
        completion_rate: 시청 완료율 (0.0 ~ 1.0)
        satisfaction:    만족도 점수 (0.0 ~ 5.0, NULL이면 0.0)
        is_rewatch:      재시청 여부
        days_ago:        현재 기준 경과일 수 (float)
    """
    vod_id: str
    strt_dt: datetime
    completion_rate: float
    satisfaction: float
    is_rewatch: bool
    days_ago: float = field(init=False)

    def __post_init__(self) -> None:
        self.days_ago = (datetime.now() - self.strt_dt).total_seconds() / 86400

    @classmethod
    def from_dict(cls, row: dict) -> "WatchRecord":
        """
        DB row dict → WatchRecord 변환.
        satisfaction이 None이면 0.0으로 대체.
        """
        return cls(
            vod_id=row["vod_id_fk"],
            strt_dt=row["strt_dt"],
            completion_rate=float(row["completion_rate"]),
            satisfaction=float(row["satisfaction"] or 0.0),
            is_rewatch=bool(row["is_rewatch"]),
        )


# ---------------------------------------------------------------------------
# HistoryLoader
# ---------------------------------------------------------------------------

class HistoryLoader:
    """
    watch_history 테이블에서 사용자 시청이력을 조회한다.

    Args:
        default_limit:       기본 조회 건수 (최근 N건)
        default_min_completion: 기본 최소 시청 완료율 필터
    """

    def __init__(
        self,
        default_limit: int = 100,
        default_min_completion: float = 0.0,
    ) -> None:
        self.default_limit = default_limit
        self.default_min_completion = default_min_completion

    def load(
        self,
        user_id: Optional[str],
        limit: Optional[int] = None,
        min_completion: Optional[float] = None,
    ) -> list[WatchRecord]:
        """
        사용자의 시청이력을 조회하여 WatchRecord 리스트로 반환.

        Args:
            user_id:        users.sha2_hash 값
            limit:          조회할 최대 건수 (기본 default_limit)
            min_completion: 이 값 이상의 completion_rate만 조회 (기본 default_min_completion)

        Returns:
            WatchRecord 리스트 (strt_dt 내림차순 정렬)

        Raises:
            ValueError: user_id가 None이거나 빈 문자열인 경우
        """
        if not user_id:
            raise ValueError("user_id는 비어 있을 수 없습니다.")

        _limit          = limit          if limit          is not None else self.default_limit
        _min_completion = min_completion if min_completion is not None else self.default_min_completion

        logger.debug(
            "시청이력 조회 — user_id=%s, limit=%d, min_completion=%.2f",
            user_id, _limit, _min_completion,
        )

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        vod_id_fk,
                        strt_dt,
                        completion_rate,
                        satisfaction,
                        is_rewatch
                    FROM watch_history
                    WHERE user_id_fk     = %s
                      AND completion_rate >= %s
                    ORDER BY strt_dt DESC
                    LIMIT %s
                    """,
                    (user_id, _min_completion, _limit),
                )
                rows = fetch_all_as_dict(cur)

        records = [WatchRecord.from_dict(row) for row in rows]
        logger.debug("  조회 완료: %d건", len(records))
        return records
