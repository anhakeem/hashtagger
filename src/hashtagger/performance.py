"""Performance feedback loop (architecture §3 post_performance, v2).

Records how generated hashtags actually performed so recommendations can learn
from real engagement instead of only static trend data. This is the moat the
research identified: the LLM is commoditized; the data is not.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS post_performance (
    id            TEXT PRIMARY KEY,
    generation_id TEXT NOT NULL,
    platform      TEXT NOT NULL,
    tag           TEXT NOT NULL,
    impressions   INTEGER NOT NULL DEFAULT 0,
    engagements   INTEGER NOT NULL DEFAULT 0,
    recorded_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_perf_gen ON post_performance(generation_id);
CREATE INDEX IF NOT EXISTS idx_perf_tag ON post_performance(tag);
"""


class PerformanceStore:
    """SQLite-backed store of per-tag post performance."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._lock = threading.Lock()
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, *, generation_id: str, platform: str, tag: str,
               impressions: int = 0, engagements: int = 0) -> str:
        row_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO post_performance (id, generation_id, platform, tag,"
                " impressions, engagements, recorded_at) VALUES (?,?,?,?,?,?,?)",
                (row_id, generation_id, platform, tag, int(impressions), int(engagements),
                 datetime.now(timezone.utc).isoformat()),
            )
            self._conn.commit()
        return row_id

    def for_generation(self, generation_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM post_performance WHERE generation_id = ? ORDER BY recorded_at ASC",
                (generation_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def tag_stats(self, tag: str) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(impressions),0) AS imp, COALESCE(SUM(engagements),0) AS eng"
                " FROM post_performance WHERE tag = ?",
                (tag,),
            ).fetchone()
        imp, eng = int(row["imp"]), int(row["eng"])
        return {
            "tag": tag,
            "impressions": imp,
            "engagements": eng,
            "engagement_rate": (eng / imp) if imp else 0.0,
        }

    def top_tags(self, *, platform: str | None = None, limit: int = 10) -> list[dict]:
        sql = ("SELECT tag, COALESCE(SUM(impressions),0) AS imp,"
               " COALESCE(SUM(engagements),0) AS eng FROM post_performance")
        params: list = []
        if platform:
            sql += " WHERE platform = ?"
            params.append(platform)
        sql += " GROUP BY tag HAVING imp > 0"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            imp, eng = int(r["imp"]), int(r["eng"])
            out.append({"tag": r["tag"], "impressions": imp, "engagements": eng,
                        "engagement_rate": eng / imp if imp else 0.0})
        out.sort(key=lambda d: d["engagement_rate"], reverse=True)
        return out[: max(1, limit)]

    def close(self) -> None:
        self._conn.close()
