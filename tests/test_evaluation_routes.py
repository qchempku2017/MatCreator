from __future__ import annotations

import sys
from pathlib import Path

import asyncio
from collections import deque

from fastapi.testclient import TestClient


WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import main


def test_create_evaluation_campaign_reads_json_body(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main, "_evaluation_store_for_owner", lambda _owner: main.EvaluationStore(tmp_path / "evaluations.db"))
    monkeypatch.setattr(main, "_evaluation_workspace_for_owner", lambda _owner: tmp_path / "workspaces")
    client = TestClient(main.app)

    response = client.post(
        "/api/evaluations/campaigns?user_id=user",
        json={
            "model_name": "matcreator",
            "question_ids": ["question-1"],
            "max_parallelism": 1,
            "max_turns": 50,
            "timeout_seconds": 600,
            "flash": False,
        },
    )

    assert response.status_code == 201, response.json()
    assert response.json()["configuration"]["question_ids"] == ["question-1"]


def test_managed_evaluation_runtime_creates_adk_session_and_run(monkeypatch, tmp_path) -> None:
    class FakeRun:
        run_id = "managed-run-1"
        status = "completed"
        error = None
        events = deque()

    calls = []

    async def fake_prepare(**kwargs):
        calls.append(("session", kwargs))

    async def fake_start(**kwargs):
        calls.append(("run", kwargs))
        run = FakeRun()
        run.task = asyncio.create_task(asyncio.sleep(0))
        return run

    monkeypatch.setattr(main, "_prepare_evaluation_adk_session", fake_prepare)
    monkeypatch.setattr(main, "_start_managed_run", fake_start)

    async def exercise():
        workspace = tmp_path / "evaluation"
        prompt = workspace / "prompt.txt"
        workspace.mkdir()
        prompt.write_text("Benchmark prompt", encoding="utf-8")
        linked = []
        outcome = await main._ManagedAdkEvaluationRuntime("user").run(
            main.RuntimeSpec(
                workspace=workspace,
                runtime_home=workspace / ".runtime",
                prompt_path=prompt,
                session_id="eval-session",
                max_turns=10,
                timeout_seconds=10,
                on_managed_run_started=lambda run_id: _link(linked, run_id),
            )
        )
        assert outcome.exit_code == 0
        assert linked == ["managed-run-1"]

    async def _link(linked, run_id):
        linked.append(run_id)

    asyncio.run(exercise())
    assert calls[0][0] == "session"
    assert calls[0][1]["session_id"] == "eval-session"
    assert calls[0][1]["workspace"] == tmp_path / "evaluation"
    assert calls[1][0] == "run"
    assert calls[1][1]["payload"]["new_message"]["parts"][0]["text"] == "Benchmark prompt"


def test_cancel_evaluation_campaign_rejects_terminal_campaign(monkeypatch, tmp_path) -> None:
    store = main.EvaluationStore(tmp_path / "evaluations.db")
    campaign = store.create_campaign(owner_id="user", model_name="matcreator", configuration={})
    store.transition_campaign(campaign["campaign_id"], "cancelled")
    monkeypatch.setattr(main, "_evaluation_store_for_owner", lambda _owner: store)
    monkeypatch.setattr(main, "_evaluation_workspace_for_owner", lambda _owner: tmp_path / "workspaces")
    client = TestClient(main.app)

    response = client.post(f"/api/evaluations/campaigns/{campaign['campaign_id']}/cancel?user_id=user")

    assert response.status_code == 409, response.json()
    assert "active evaluation campaigns" in response.json()["detail"]


def test_question_set_routes_enforce_shared_read_and_owner_delete(monkeypatch, tmp_path) -> None:
    store = main.EvaluationStore(tmp_path / "evaluations.db")
    monkeypatch.setattr(main, "_evaluation_store_for_owner", lambda _owner: store)
    client = TestClient(main.app)

    created = client.post(
        "/api/evaluations/question-sets?user_id=alice",
        json={"name": "Crystal checks", "question_ids": ["question-1"], "visibility": "shared"},
    )

    assert created.status_code == 201, created.json()
    set_id = created.json()["set_id"]
    visible = client.get("/api/evaluations/question-sets?user_id=bob")
    assert visible.status_code == 200, visible.json()
    assert [item["set_id"] for item in visible.json()["question_sets"]] == [set_id]
    assert client.delete(f"/api/evaluations/question-sets/{set_id}?user_id=bob").status_code == 404
    assert client.delete(f"/api/evaluations/question-sets/{set_id}?user_id=alice").status_code == 204


def test_catalog_forwards_single_capability_and_task_type_filters(monkeypatch) -> None:
    class FakeBenchmarkClient:
        async def list_questions(self, **filters):
            assert filters["capability"] == "data_handling"
            assert filters["task_type"] == "simulation"
            return {
                "questions": [
                    {"id": "match", "capability": ["data_handling", "scientific_reasoning"], "task_type": "simulation"},
                ],
                "total": 1,
                "offset": 0,
                "limit": 100,
                "facets": {},
            }

    monkeypatch.setattr(main, "_benchmark_client", lambda: FakeBenchmarkClient())
    client = TestClient(main.app)

    response = client.get("/api/evaluations/catalog?capability=data_handling&task_type=simulation")

    assert response.status_code == 200, response.json()
    assert [question["id"] for question in response.json()["questions"]] == ["match"]
    assert response.json()["total"] == 1


def test_catalog_uses_maximum_page_size_by_default(monkeypatch) -> None:
    class FakeBenchmarkClient:
        async def list_questions(self, **filters):
            assert filters["limit"] == 500
            return {"questions": [], "total": None, "offset": 0, "limit": 500, "facets": {}}

    monkeypatch.setattr(main, "_benchmark_client", lambda: FakeBenchmarkClient())

    response = TestClient(main.app).get("/api/evaluations/catalog")

    assert response.status_code == 200, response.json()


def test_session_evaluation_question_draft_returns_bounded_observable_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "_load_session_log_export",
        lambda session_id, user_id: {
            "session_id": session_id,
            "owner_id": user_id,
            "event_count": 3,
            "artifact_count": 1,
            "artifacts": ["/tmp/result.json"],
            "graph": {
                "nodes": [
                    {
                        "step_number": 1,
                        "action": "Relax structure",
                        "summary": "Converged geometry.",
                        "status": "success",
                        "tool_call_count": 2,
                        "artifact_count": 1,
                    },
                    {"step_number": 2, "action": "Retry", "status": "failed"},
                ]
            },
        },
    )

    response = TestClient(main.app).post(
        "/api/sessions/session-1/evaluation-question-draft?user_id=alice"
    )

    assert response.status_code == 200, response.json()
    draft = response.json()
    assert draft["status"] == "draft"
    assert draft["source"] == {
        "session_id": "session-1",
        "owner_id": "alice",
        "event_count": 3,
        "artifact_count": 1,
    }
    assert draft["question"]["rubrics"] == []
    assert draft["evidence"]["successful_steps"] == [
        {
            "step_number": 1,
            "action": "Relax structure",
            "summary": "Converged geometry.",
            "tool_call_count": 2,
            "artifact_count": 1,
        }
    ]
    assert draft["evidence"]["artifacts"] == ["/tmp/result.json"]
    assert draft["publication"]["status"] == "local_preview"


def test_session_evaluation_question_draft_propagates_missing_session(monkeypatch) -> None:
    def missing_session(_session_id, _user_id):
        raise main.HTTPException(status_code=404, detail="Session not found")

    monkeypatch.setattr(main, "_load_session_log_export", missing_session)

    response = TestClient(main.app).post(
        "/api/sessions/missing/evaluation-question-draft?user_id=alice"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"