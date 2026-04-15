import json

import pytest

from chat.sse import SSEEmitter


@pytest.mark.anyio
async def test_emit_and_drain():
    emitter = SSEEmitter()
    emitter.emit("node_discovered", {"note_id": "abc", "title": "Test"})
    emitter.emit("done", {})
    emitter.close()

    events = []
    async for chunk in emitter.stream():
        events.append(chunk)

    assert len(events) == 2
    first = json.loads(events[0].removeprefix("data: ").strip())
    assert first["type"] == "node_discovered"
    assert first["data"]["note_id"] == "abc"


@pytest.mark.anyio
async def test_close_terminates_stream():
    emitter = SSEEmitter()
    emitter.close()
    events = []
    async for chunk in emitter.stream():
        events.append(chunk)
    assert events == []
