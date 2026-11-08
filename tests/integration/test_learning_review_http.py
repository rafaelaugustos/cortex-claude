import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.store import LearningStore
from cortex_claude.learning.tasks import save_task
from cortex_claude.web import server as web


def test_review_api_rejects_stale_writes_and_cross_origin_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "CORTEX_HOME", tmp_path)
    with LearningStore(tmp_path) as store:
        left = store.observe(Observation("Use pytest", "testing", "personal", "tests"), str(tmp_path), "a")
        store.observe(Observation("Use unittest", "testing", "personal", "tests"), str(tmp_path), "b")
        task = save_task(store, str(tmp_path), "a", title="Parser", summary="Partial", next_step="Run tests")
    server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.CortexHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def call(path, data=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        with urlopen(Request(f"http://127.0.0.1:{server.server_port}" + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)) as response:
            return json.load(response)
    try:
        cid = call("/api/conflicts")["items"][0]["id"]
        with pytest.raises(HTTPError) as error:
            call(f"/api/conflicts/{cid}/resolve", {"choice": "keep_left"}, "https://foreign.example")
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            call(f"/api/conflicts/{cid}/resolve", {"choice": "condition_left", "conditions": {}})
        assert error.value.code == 400
        assert call(f"/api/conflicts/{cid}/resolve", {"choice": "keep_left"})["state"] == "resolved"
        with pytest.raises(HTTPError) as error:
            call(f"/api/conflicts/{cid}/resolve", {"choice": "keep_right"})
        assert error.value.code == 400
        lid = left["id"]
        with pytest.raises(HTTPError):
            call(f"/api/learning/{lid}/feedback", {"assessment": "useful", "session_id": "assistant"})
        for _ in range(2):
            call(f"/api/learning/{lid}/feedback", {"assessment": "useful", "session_id": "dashboard:test"})
        assert call("/api/learning")["stats"]["feedback"]["useful"] == 1
        tid = task["id"]
        with pytest.raises(HTTPError) as error:
            call(f"/api/tasks/{tid}", {"action": "complete", "expected_revision": 2})
        assert error.value.code == 400
        call(f"/api/tasks/{tid}", {"action": "complete", "expected_revision": 1})
        assert call("/api/tasks")["items"][0]["state"] == "complete"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
