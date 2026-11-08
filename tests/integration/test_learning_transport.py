import asyncio
import json
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from cortex_claude.hooks import process_event
from cortex_claude.learning.extraction import Observation
from cortex_claude.learning.store import LearningStore
from cortex_claude.server.tools.learn import handle_learn


def test_dashboard_learning_http_and_forget(tmp_path, monkeypatch):
    from cortex_claude.web import server as web
    monkeypatch.setattr(web, "CORTEX_HOME", tmp_path)
    with LearningStore(tmp_path) as store:
        lesson = store.observe(Observation("Prefer small functions", "code.function-size", "personal", "code", True), "/a", "s")
    server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.CortexHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/learning") as response:
            body = json.load(response)
        assert body["lessons"][0]["id"] == lesson["id"]
        assert body["stats"]["states"]["active"] == 1
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/api/learning", headers={"Origin": "https://foreign.example"}))
        assert error.value.code == 403
        with urlopen(Request(base + "/api/learning/" + lesson["id"], method="DELETE")) as response:
            assert json.load(response)["ok"]
        with urlopen(base + "/api/learning") as response:
            assert json.load(response)["lessons"] == []
        with urlopen(base + "/") as response:
            assert b'<div id="root">' in response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_raw_capture_redacts_before_truncation(tmp_path, monkeypatch):
    from cortex_claude import hooks
    (tmp_path / "config.json").write_text('{"learning":{"capture_tools":true}}')
    sent = []
    monkeypatch.setattr(hooks, "_send", lambda home, payload, **kwargs: sent.append(payload))
    process_event("PostToolUse", {
        "cwd": "/a", "session_id": "s", "tool_name": "WebFetch",
        "tool_response": "A useful bug fix. " + "<private>" + "SECRET " * 1000 + "</private>" + "Public architectural decision. " * 10,
    }, tmp_path)
    assert sent
    assert "SECRET" not in json.dumps(sent)
    assert "Public architectural decision" in sent[0]["content"]


def test_manual_learning_does_not_double_count_a_user_prompt(tmp_path):
    for sid in ["session-a", "session-b"]:
        process_event("UserPromptSubmit", {"cwd": "/a", "session_id": sid, "prompt": "Prefiro funções pequenas"}, tmp_path)
    result = json.loads(handle_learn(tmp_path, "/a", content="I prefer small functions",
                                    topic="code.function-size", applicability="personal", triggers="code function"))
    assert result["confirmations"] == 2
    assert result["status"] == "candidate"


@pytest.mark.asyncio
async def test_daemon_reads_fragmented_socket_messages():
    from cortex_claude.daemon import CortexDaemon
    daemon = object.__new__(CortexDaemon)

    async def dispatch(action, payload):
        return {"ok": True, "content_length": len(payload["content"])}
    daemon._dispatch = dispatch
    with tempfile.TemporaryDirectory(prefix="cx-sock-", dir="/tmp") as tmp:
        socket_path = str(Path(tmp) / "test.sock")
        server = await asyncio.start_unix_server(daemon.handle_client, path=socket_path)
        async with server:
            reader, writer = await asyncio.open_unix_connection(socket_path)
            request = json.dumps({"action": "save", "content": "x" * 80000}).encode()
            writer.write(request[:20])
            await writer.drain()
            await asyncio.sleep(.01)
            writer.write(request[20:])
            writer.write_eof()
            await writer.drain()
            response = json.loads(await asyncio.wait_for(reader.read(), timeout=3))
            assert response == {"ok": True, "content_length": 80000}
            writer.close()
            await writer.wait_closed()
