"""
DB 연결 헬퍼
"""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

import config


@contextmanager
def get_conn():
    """트랜잭션 단위 연결 컨텍스트 매니저"""
    conn = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all_as_dict(cur):
    """커서 결과를 dict 리스트로 변환"""
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
