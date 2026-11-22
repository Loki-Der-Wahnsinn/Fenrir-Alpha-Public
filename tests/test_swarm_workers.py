import swarm_workers


def test_swarm_worker_sends_hive_token_on_register_and_submit(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"status": "ok"}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(swarm_workers, "HEADERS", {"X-Fenrir-Token": "test-token"})
    monkeypatch.setattr(swarm_workers.requests, "post", fake_post)

    worker = swarm_workers.MicroWorker(1)
    worker.register()
    worker.process_task({"task_id": "t-1", "task_type": "unknown", "payload": {}})

    assert len(calls) == 2
    assert calls[0][0].endswith("/register_node")
    assert calls[0][1]["headers"] == {"X-Fenrir-Token": "test-token"}
    assert "/submit_result" in calls[1][0]
    assert calls[1][1]["headers"] == {"X-Fenrir-Token": "test-token"}


def test_swarm_worker_reports_missing_web_search_cleanly(monkeypatch):
    submitted = []

    class FakeResponse:
        status_code = 200

    def fake_post(url, **kwargs):
        submitted.append(kwargs["json"])
        return FakeResponse()

    monkeypatch.setattr(swarm_workers.requests, "post", fake_post)
    worker = swarm_workers.MicroWorker(2)
    worker.search_tool = None
    worker.process_task({"task_id": "t-2", "task_type": "web_search", "payload": {"query": "test"}})

    assert submitted[0]["result"]["status"] == "error"
    assert "WebSearchTool" in submitted[0]["result"]["message"]
