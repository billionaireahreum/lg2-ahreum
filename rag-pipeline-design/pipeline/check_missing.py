"""
결측값 현황 조회
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import db

QUERY = """
SELECT
    COUNT(*)                                        AS total,

    -- 핵심 컬럼별 NULL / 빈문자열
    COUNT(*) FILTER (WHERE title        IS NULL OR title        = '') AS missing_title,
    COUNT(*) FILTER (WHERE genre        IS NULL OR genre        = '') AS missing_genre,
    COUNT(*) FILTER (WHERE director     IS NULL OR director     = '') AS missing_director,
    COUNT(*) FILTER (WHERE actor        IS NULL OR actor        = '') AS missing_actor,
    COUNT(*) FILTER (WHERE smry         IS NULL OR smry         = '') AS missing_smry,
    COUNT(*) FILTER (WHERE age          IS NULL OR age          = '') AS missing_age,
    COUNT(*) FILTER (WHERE release_date IS NULL)                      AS missing_release_date,

    -- 임베딩
    COUNT(*) FILTER (WHERE embedding    IS NULL)                      AS missing_embedding,

    -- rag_processed 플래그
    COUNT(*) FILTER (WHERE rag_processed = TRUE)                      AS rag_processed_true,
    COUNT(*) FILTER (WHERE rag_processed IS NULL OR rag_processed = FALSE) AS rag_processed_false

FROM vod_contents;
"""

DETAIL_QUERY = """
SELECT
    genre,
    COUNT(*)                                                  AS total,
    COUNT(*) FILTER (WHERE director IS NULL OR director = '') AS miss_dir,
    COUNT(*) FILTER (WHERE smry     IS NULL OR smry     = '') AS miss_smry
FROM vod_contents
GROUP BY genre
ORDER BY total DESC
LIMIT 20;
"""

def main():
    with db.get_conn() as conn:
        cur = conn.cursor()

        print("=" * 55)
        print("  전체 결측값 현황")
        print("=" * 55)
        cur.execute(QUERY)
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        for col, val in zip(cols, row):
            pct = f"  ({val/row[0]*100:.1f}%)" if col != "total" and row[0] else ""
            print(f"  {col:<28}: {val:>8}{pct}")

        print()
        print("=" * 55)
        print("  장르별 감독/줄거리 결측 (상위 20)")
        print("=" * 55)
        cur.execute(DETAIL_QUERY)
        rows = cur.fetchall()
        print(f"  {'장르':<20} {'전체':>7} {'감독결측':>8} {'줄거리결측':>10}")
        print("  " + "-" * 48)
        for r in rows:
            genre = str(r[0] or "(null)")[:20]
            print(f"  {genre:<20} {r[1]:>7} {r[2]:>8} {r[3]:>10}")

if __name__ == "__main__":
    main()
