import json

import httpx
import pytest

from app.db import Database
from app.llm import LLMClient, LLMError, extract_json
from app.schemas import AgentStep, Audience, OutputType, ResearchRequest, ResearchRun
from tests.helpers import make_settings


# ---------------------------------------------------------------- LLM client
def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here you go: {"a": {"b": 2}} Hope that helps') == {"a": {"b": 2}}
    for bad in ["no json here", "[1, 2]", ""]:
        with pytest.raises(LLMError):
            extract_json(bad)


def client_with(handler, **settings_kwargs):
    settings = make_settings(settings_kwargs.pop("tmp"), **settings_kwargs)
    return LLMClient(settings, http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)


def test_not_configured_raises_clear_error(tmp_path):
    llm = LLMClient(make_settings(tmp_path))
    assert not llm.enabled and llm.info.provider == "none"
    with pytest.raises(LLMError):
        llm.complete("s", "u")
    broken = LLMClient(make_settings(tmp_path, llm_provider="anthropic", llm_api_key=""))
    assert not broken.enabled


def test_openai_request_shape_and_parsing(tmp_path):
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers.get("authorization"), json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    llm = client_with(handler, tmp=tmp_path, llm_provider="openai", llm_api_key="sk-test", llm_model="m1")
    assert llm.complete_json("sys", "usr") == {"ok": True}
    assert seen["url"] == "https://api.openai.com/v1/chat/completions" and seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "m1" and seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_openai_compatible_base_url_and_no_key(tmp_path):
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers.get("authorization"), json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    llm = client_with(handler, tmp=tmp_path, llm_provider="openai", llm_base_url="http://localhost:11434/v1/", llm_model="llama")
    assert llm.enabled
    llm.complete("s", "u", json_mode=True)
    assert seen["url"] == "http://localhost:11434/v1/chat/completions" and seen["auth"] is None
    assert "max_tokens" in seen["body"] and "response_format" not in seen["body"]


def test_anthropic_request_shape_and_parsing(tmp_path):
    seen = {}

    def handler(request):
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers.get("x-api-key"), json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"x": 1}'}]})

    llm = client_with(handler, tmp=tmp_path, llm_provider="anthropic", llm_api_key="ak-test")
    assert llm.complete_json("sys", "usr") == {"x": 1}
    assert seen["url"] == "https://api.anthropic.com/v1/messages" and seen["key"] == "ak-test"
    assert seen["body"]["system"] == "sys" and seen["body"]["messages"] == [{"role": "user", "content": "usr"}]


def test_http_errors_are_readable_and_never_leak_the_key(tmp_path):
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})

    llm = client_with(handler, tmp=tmp_path, llm_provider="openai", llm_api_key="sk-SECRET")
    with pytest.raises(LLMError) as info:
        llm.complete("s", "u")
    assert "401" in str(info.value) and "Incorrect API key" in str(info.value) and "sk-SECRET" not in str(info.value)


def test_retries_on_rate_limit_then_succeeds(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    llm = client_with(handler, tmp=tmp_path, llm_provider="openai", llm_api_key="k")
    assert llm.complete_json("s", "u") == {} and calls["n"] == 2


def test_invalid_json_is_retried_once_then_reported(tmp_path):
    llm = client_with(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}),
                      tmp=tmp_path, llm_provider="openai", llm_api_key="k")
    with pytest.raises(LLMError, match="valid JSON"):
        llm.complete_json("s", "u")


# ---------------------------------------------------------------- database
def make_run(run_id="r1", question="Does exercise help mood in adults?"):
    return ResearchRun(id=run_id, question=question, audience=Audience.general_public, output_type=OutputType.research_summary,
                       steps=[AgentStep(key="research", name="Research Agent", status="running")], status="running")


def test_database_round_trip_list_and_delete(tmp_path):
    db = Database(tmp_path / "sub" / "t.db")
    db.init()
    db.save_run(make_run("a"))
    second = make_run("b", "Second question about vaccines?")
    db.save_run(second)
    second.status = "completed"
    db.save_run(second)  # upsert, not a duplicate

    assert db.get_run("zzz") is None
    assert db.get_run("b").status == "completed"
    summaries = db.list_runs()
    assert [s.id for s in summaries] == ["b", "a"]
    assert db.delete_run("a") is True and db.delete_run("a") is False
    assert [s.id for s in db.list_runs()] == ["b"]


def test_interrupted_runs_are_marked_failed_on_startup(tmp_path):
    db = Database(tmp_path / "t.db")
    db.init()
    db.save_run(make_run("stuck"))
    assert db.mark_interrupted() == 1
    run = db.get_run("stuck")
    assert run.status == "failed" and "interrupted" in run.error and run.steps[0].status == "failed"
    assert db.mark_interrupted() == 0
