from __future__ import annotations

import math
import sqlite3
import time


def recalculate_decay_scores(
    conn: sqlite3.Connection,
    decay_lambda: float = 0.05,
    min_score: float = 0.01,
) -> int:
    now_ms = int(time.time() * 1000)
    rows = conn.execute(
        "SELECT id, accessed_at, access_count FROM memories"
    ).fetchall()

    updated = 0
    for row in rows:
        days_since = (now_ms - row["accessed_at"]) / 86_400_000
        access_boost = math.log(1 + row["access_count"])
        score = max(math.exp(-decay_lambda * days_since) * (1 + access_boost), min_score)

        conn.execute(
            "UPDATE memories SET decay_score = ? WHERE id = ?",
            (score, row["id"]),
        )
        updated += 1

    conn.commit()
    return updated
