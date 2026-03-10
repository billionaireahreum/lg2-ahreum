"""
DB 연결 헬퍼
"""
import getpass
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

import config

_password_cache = None


def _get_password() -> str:
    global _password_cache
    if config.DB_PASSWORD:
        return config.DB_PASSWORD
    if _password_cache is None:
        _password_cache = getpass.getpass("PostgreSQL 비밀번호 입력: ")
    return _password_cache


@contextmanager
def get_conn():
    """트랜잭션 단위 연결 컨텍스트 매니저"""
    conn_params = dict(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=_get_password(),
    )
    conn = psycopg2.connect(**conn_params)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all_as_dict(cur) -> list[dict]:
    """커서 결과를 dict 리스트로 변환"""
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
