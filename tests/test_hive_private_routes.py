import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import distributed_core as dc


@pytest.fixture
def hive(monkeypatch):
    monkeypatch.setattr(dc, "HIVE_TOKEN", "test-token")
    monkeypatch.setattr(dc, "MESSAGES_FOR_CORE", [])
    monkeypatch.setattr(dc, "MESSAGES_FOR_UI", [])
    monkeypatch.setattr(dc, "COMPLETED_TASKS", {})
    with TestClient(dc.app) as client:
        yield client


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/ui/message/send", {"message": "hello"}),
        ("get", "/ui/message/poll_for_core", None),
        ("post", "/ui/message/from_core", {"message": "hello"}),
        ("get", "/ui/message/poll", None),
        ("get", "/tasks/result/task-1", None),
        ("get", "/queue_size", None),
        ("post", "/generate", {"prompt": "hello"}),
        ("post", "/api/generate", {"prompt": "hello"}),
    ],
)
def test_private_routes_reject_missing_and_invalid_token(hive, method, path, body):
    for headers in ({}, {"X-Fenrir-Token": "incorrect"}):
        response = hive.request(method, path, headers=headers, json=body)
        assert response.status_code == 401


def test_denied_reads_do_not_consume_private_data(hive):
    dc.MESSAGES_FOR_CORE.append("private")
    dc.COMPLETED_TASKS["task-1"] = {"private": True}
    assert hive.get("/ui/message/poll_for_core").status_code == 401
    assert hive.get("/tasks/result/task-1").status_code == 401
    headers = {"X-Fenrir-Token": "test-token"}
    assert hive.get("/ui/message/poll_for_core", headers=headers).json() == {"messages": ["private"]}
    assert hive.get("/tasks/result/task-1", headers=headers).json()["result"] == {"private": True}


def test_authorized_messages_work_in_both_directions(hive):
    headers = {"X-Fenrir-Token": "test-token"}
    assert hive.post("/ui/message/send", headers=headers, json={"message": "to core"}).status_code == 200
    assert hive.get("/ui/message/poll_for_core", headers=headers).json() == {"messages": ["to core"]}
    assert hive.post("/ui/message/from_core", headers=headers, json={"message": "to UI"}).status_code == 200
    assert hive.get("/ui/message/poll", headers=headers).json() == {"messages": ["to UI"]}


@pytest.mark.parametrize("path", ["/generate", "/api/generate"])
def test_proxy_only_forwards_authorized_requests(hive, monkeypatch, path):
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"response": "ok"}

    class FakeClient:
        async def post(self, url, json):
            calls.append((url, json))
            return FakeResponse()

    monkeypatch.setattr(dc, "_MINISTRY_CLIENT", FakeClient())
    body = {"prompt": "private"}
    assert hive.post(path, json=body).status_code == 401
    assert calls == []
    response = hive.post(path, json=body, headers={"X-Fenrir-Token": "test-token"})
    assert response.status_code == 200
    assert response.json() == {"response": "ok"}
    assert calls == [("http://127.0.0.1:8001/generate", body)]


@pytest.mark.parametrize("path", ["/ws/swarm_status", "/ws/logs", "/ws/sdr"])
def test_private_websockets_require_token(hive, path):
    for suffix in ("", "?token=incorrect", "?token=%C3%A4"):
        with pytest.raises(WebSocketDisconnect) as error:
            with hive.websocket_connect(path + suffix):
                pass
        assert error.value.code == 1008
    with hive.websocket_connect(f"{path}?token=test-token"):
        pass


def test_legacy_mode_remains_available_without_token(hive, monkeypatch):
    monkeypatch.setattr(dc, "HIVE_TOKEN", "")
    assert hive.post("/ui/message/send", json={"message": "hello"}).status_code == 200
    assert hive.get("/ui/message/poll_for_core").json() == {"messages": ["hello"]}


def test_hive_defaults_to_loopback_and_requires_explicit_external_bind(monkeypatch):
    calls = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            calls.append((target, args, daemon))

        def start(self):
            pass

    class FakeCortex:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(dc, "Thread", FakeThread)
    monkeypatch.setattr(dc, "SDRCortex", FakeCortex)
    monkeypatch.setattr(dc, "sdr_cortex_instance", None, raising=False)
    monkeypatch.setattr(dc, "HIVE_TOKEN", "test-token")
    monkeypatch.delenv("FENRIR_HIVE_HOST", raising=False)
    dc.start_master_api(port=8123)
    assert calls[-1] == (dc.run_server, ("127.0.0.1", 8123), True)
    monkeypatch.setenv("FENRIR_HIVE_HOST", "0.0.0.0")
    dc.start_master_api(port=8123)
    assert calls[-1] == (dc.run_server, ("0.0.0.0", 8123), True)
    dc.start_master_api(host="127.0.0.2", port=8124)
    assert calls[-1] == (dc.run_server, ("127.0.0.2", 8124), True)
    monkeypatch.setenv("FENRIR_HIVE_HOST", " ")
    with pytest.raises(ValueError):
        dc.start_master_api()


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.1", "localhost"])
def test_no_token_prevents_network_or_hostname_bind(monkeypatch, host):
    monkeypatch.setattr(dc, "HIVE_TOKEN", "")
    with pytest.raises(ValueError, match="FENRIR_HIVE_TOKEN"):
        dc.start_master_api(host=host)
    with pytest.raises(ValueError, match="FENRIR_HIVE_TOKEN"):
        dc.run_server(host, 8123)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1"])
def test_loopback_bind_is_allowed_without_token(monkeypatch, host):
    monkeypatch.setattr(dc, "HIVE_TOKEN", "")
    assert dc.validate_hive_bind(host) == host


def test_untrusted_host_and_origin_headers_are_rejected(hive):
    headers = {"X-Fenrir-Token": "test-token", "Host": "evil.example"}
    assert hive.get("/queue_size", headers=headers).status_code == 400
    origin_headers = {"X-Fenrir-Token": "test-token", "Origin": "https://evil.example"}
    assert hive.post("/ui/message/send", headers=origin_headers, json={"message": "x"}).status_code == 403
    ok_origin = {"X-Fenrir-Token": "test-token", "Origin": "http://127.0.0.1:3000"}
    assert hive.post("/ui/message/send", headers=ok_origin, json={"message": "ok"}).status_code == 200
