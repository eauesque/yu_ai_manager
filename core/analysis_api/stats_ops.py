"""Analysis stats operations."""

from core.services_core.db_api import get_readonly_db


def get_analysis_stats():
    con = get_readonly_db()
    try:
        total_analyzed = con.execute("SELECT COUNT(*) FROM analysis").fetchone()[0]
        total_files = con.execute("SELECT COUNT(*) FROM files WHERE is_deleted=0").fetchone()[0]
        styles = con.execute(
            """
            SELECT style, COUNT(*) as cnt FROM analysis
            WHERE style IS NOT NULL AND style != ''
            GROUP BY style ORDER BY cnt DESC, style ASC LIMIT 10
        """
        )
        quality_dist = con.execute(
            """
            SELECT
                CASE
                    WHEN quality_score >= 8 THEN 'excellent'
                    WHEN quality_score >= 6 THEN 'good'
                    WHEN quality_score >= 4 THEN 'average'
                    ELSE 'low'
                END as tier,
                COUNT(*) as cnt,
                ROUND(AVG(quality_score), 1) as avg_score
            FROM analysis
            WHERE quality_score > 0
            GROUP BY tier
            ORDER BY tier
        """
        )
        return {
            "total_analyzed": total_analyzed,
            "total_files": total_files,
            "styles": [{"style": r[0], "count": r[1]} for r in styles],
            "quality_distribution": [{"tier": r[0], "count": r[1], "avg_score": r[2]} for r in quality_dist],
        }, 200
    except Exception:
        return {"total_analyzed": 0, "total_files": 0, "styles": [], "quality_distribution": []}, 200
