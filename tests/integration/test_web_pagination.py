from cortex_claude.storage.database import StorageManager
from cortex_claude.web import server as web


def test_archive_pages_merge_scopes_without_losing_or_repeating_memories(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "CORTEX_HOME", tmp_path)
    storage = StorageManager(tmp_path)
    for scope, count in [("global", 25), ("project:small", 5)]:
        conn = storage.get_database(scope)
        with conn:
            for i in range(count):
                conn.execute("INSERT INTO memories(id,content,scope,created_at,updated_at,accessed_at) VALUES (?,?,?,?,?,?)", (f"{scope}-{i}", f"Note {i}", scope, i, i, i))
    ids = []
    timestamps = []
    for offset in range(0, 30, 7):
        page = web.api_memories(None, None, None, None, "recent", 7, offset)
        assert page["total"] == 30
        ids.extend(item["id"] for item in page["items"])
        timestamps.extend(item["created_at"] for item in page["items"])
    assert len(ids) == len(set(ids)) == 30
    assert timestamps == sorted(timestamps, reverse=True)
    storage.close_all()
