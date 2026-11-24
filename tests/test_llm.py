import json
import re
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

import bowerbird.profile
from bowerbird import categorize, db, llm, models
from bowerbird.server import create_app

SCHEMA = {"type": "object", "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
          "required": ["queries"], "additionalProperties": False}


def completion(text, finish_reason="stop"):
    return httpx.Response(200, json={"choices": [
        {"finish_reason": finish_reason, "message": {"role": "assistant", "content": text}}]})


@pytest.fixture
def openai(monkeypatch):
    """Point the OpenAI-compatible path at a mock server; returns a recorder."""
    real = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client",
                        lambda **kw: real(transport=httpx.MockTransport(handle), **kw))
    requests = []
    handler = None

    def handle(request):
        requests.append(request)
        assert handler is not None, "call install(server) before anything is fetched"
        return handler(request)

    monkeypatch.setenv("BOWERBIRD_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOWERBIRD_CHAT_MODEL", "llama3")

    def install(server):
        nonlocal handler
        handler = server
        return requests

    return install


def bodies(requests):
    return [json.loads(r.content) for r in requests]


# ---------- OpenAI-compatible ----------

def test_openai_path_sends_schema_and_parses_the_answer(openai):
    requests = openai(lambda request: completion('{"queries": ["bed levelling"]}'))
    assert llm.complete("find", SCHEMA, 1500, model="llama3") == {"queries": ["bed levelling"]}
    request = requests[0]
    assert str(request.url) == "http://localhost:11434/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    body = bodies(requests)[0]
    assert body["model"] == "llama3" and body["max_tokens"] == 1500
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["messages"] == [{"role": "user", "content": "find"}]


def test_openai_path_needs_no_key_for_a_local_server(openai, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    requests = openai(lambda request: completion('{"queries": []}'))
    llm.complete("find", SCHEMA, 100, model="llama3")
    assert "authorization" not in requests[0].headers


def test_openai_path_puts_the_system_prompt_first(openai):
    requests = openai(lambda request: completion('{"queries": []}'))
    llm.complete("do it", SCHEMA, 100, model="llama3", system="rules")
    assert [m["role"] for m in bodies(requests)[0]["messages"]] == ["system", "user"]


def test_openai_path_falls_back_when_structured_output_is_not_understood(openai):
    def server(request):
        if "response_format" in json.loads(request.content):
            return httpx.Response(400, json={"error": {"message": "unknown field: response_format"}})
        return completion('```json\n{"queries": ["x"]}\n```')

    requests = openai(server)
    assert llm.complete("find", SCHEMA, 100, model="llama3") == {"queries": ["x"]}
    _, second = bodies(requests)
    assert "response_format" not in second
    assert second["messages"][0]["role"] == "system" and second["messages"][1]["content"] == "find"


def test_openai_path_renames_the_token_limit_when_asked(openai):
    def server(request):
        if "max_tokens" in json.loads(request.content):
            return httpx.Response(400, json={"error": {
                "message": "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead."}})
        return completion('{"queries": []}')

    requests = openai(server)
    llm.complete("find", SCHEMA, 321, model="llama3")
    body = bodies(requests)[-1]
    assert body["max_completion_tokens"] == 321 and "max_tokens" not in body


def test_openai_path_refusal_is_none(openai):
    openai(lambda request: completion("", finish_reason="content_filter"))
    assert llm.complete("find", SCHEMA, 100, model="llama3") is None


def test_openai_path_rejected_key_is_a_mistake_on_our_side(openai):
    openai(lambda request: httpx.Response(401, json={"error": {"message": "invalid api key"}}))
    with pytest.raises(llm.LLMError) as caught:
        llm.complete("find", SCHEMA, 100, model="llama3")
    assert caught.value.status == 401 and "OPENAI_API_KEY" in (caught.value.advice or "")
    assert "invalid api key" in str(caught.value)


def test_openai_path_unknown_model_points_at_the_settings(openai):
    openai(lambda request: httpx.Response(404, json={"error": {"message": "model 'llama3' not found"}}))
    with pytest.raises(llm.LLMError) as caught:
        llm.complete("find", SCHEMA, 100, model="llama3")
    assert "BOWERBIRD_TAXONOMY_MODEL" in (caught.value.advice or "")


def test_openai_path_catches_anthropic_model_ids(openai, monkeypatch):
    for var in llm.MODEL_VARIABLES:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(llm.LLMError) as caught:
        llm.complete("find", SCHEMA, 100, model=models.ASSIGN_DEFAULT)
    assert "BOWERBIRD_ASSIGN_MODEL" in (caught.value.advice or "")


def test_unreadable_answer_is_an_error(openai):
    openai(lambda request: completion("Sure, here you go!"))
    with pytest.raises(llm.LLMError, match="not a JSON object"):
        llm.complete("find", SCHEMA, 100, model="llama3")


def test_base_url_without_a_scheme_is_refused(openai, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "localhost:11434/v1")
    openai(lambda request: completion('{"queries": []}'))
    with pytest.raises(llm.LLMError) as caught:
        llm.complete("find", SCHEMA, 100, model="llama3")
    assert "OPENAI_BASE_URL" in str(caught.value)


def test_unknown_provider_is_refused(monkeypatch):
    monkeypatch.setenv("BOWERBIRD_LLM_PROVIDER", "gemini")
    with pytest.raises(llm.LLMError, match="BOWERBIRD_LLM_PROVIDER"):
        llm.complete("find", SCHEMA, 100, model="m")


def test_assign_runs_over_an_openai_compatible_server(openai, monkeypatch, tmp_path):
    monkeypatch.setenv("BOWERBIRD_ASSIGN_MODEL", "llama3")
    conn = db.connect(tmp_path / "test.db")
    conn.execute("INSERT INTO categories(id, path) VALUES(1,'Printing')")
    conn.executemany("INSERT INTO urls(id, canonical_url, check_url, status) VALUES(?,?,?,'live')",
                     [(1, "https://e.com/a", "https://e.com/a"), (2, "https://e.com/b", "https://e.com/b")])
    conn.commit()

    def server(request):
        listing = json.loads(request.content)["messages"][-1]["content"]
        items = [{"index": i, "categories": [{"path": "Printing", "confidence": 0.9}]}
                 for i in range(len(re.findall(r"^\[\d+\]", listing, re.MULTILINE)))]
        return completion(json.dumps({"items": items}))

    openai(server)
    assert categorize.assign(conn) == {"assigned": 2, "skipped": 0, "batches": 1}
    assert [tuple(r) for r in conn.execute(
        "SELECT source, model, COUNT(*) FROM url_categories GROUP BY source, model")] == [("llm", "llama3", 2)]


# ---------- Anthropic ----------

class FakeAnthropic:
    def __init__(self, stop_reason="end_turn", raise_=None):
        self.stop_reason, self.raise_, self.sent = stop_reason, raise_, None
        self.messages = self

    def create(self, **kwargs):
        self.sent = kwargs
        if self.raise_:
            raise self.raise_
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text='{"queries": []}')])


@pytest.fixture
def anthropic_sdk(monkeypatch):
    monkeypatch.delenv("BOWERBIRD_LLM_PROVIDER", raising=False)

    def install(fake):
        monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: fake)
        return fake

    return install


def test_anthropic_path_caches_the_system_prompt_and_sends_no_effort(anthropic_sdk):
    fake = anthropic_sdk(FakeAnthropic())
    assert llm.complete("sort", SCHEMA, 8000, model="m", system="rules") == {"queries": []}
    assert fake.sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert fake.sent["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    assert fake.sent["messages"] == [{"role": "user", "content": "sort"}]


def test_anthropic_path_passes_effort_when_given(anthropic_sdk):
    fake = anthropic_sdk(FakeAnthropic())
    llm.complete("sort", SCHEMA, 1500, model="m", effort="low")
    assert fake.sent["output_config"]["effort"] == "low"


def test_anthropic_path_refusal_is_none(anthropic_sdk):
    anthropic_sdk(FakeAnthropic(stop_reason="refusal"))
    assert llm.complete("sort", SCHEMA, 100, model="m") is None


def test_anthropic_path_missing_key_is_a_mistake_on_our_side(anthropic_sdk):
    anthropic_sdk(FakeAnthropic(raise_=TypeError("Could not resolve authentication method.")))
    with pytest.raises(llm.LLMError) as caught:
        llm.complete("sort", SCHEMA, 100, model="m")
    assert "ANTHROPIC_API_KEY" in (caught.value.advice or "") and str(caught.value).endswith("set ANTHROPIC_API_KEY")


def test_anthropic_path_api_failure_keeps_the_status(anthropic_sdk):
    request = httpx.Request("POST", "https://api.anthropic.com")
    too_busy = anthropic.RateLimitError(message="rate limited", response=httpx.Response(429, request=request), body=None)
    anthropic_sdk(FakeAnthropic(raise_=too_busy))
    with pytest.raises(llm.LLMError) as caught:
        llm.complete("sort", SCHEMA, 100, model="m")
    assert caught.value.status == 429 and caught.value.advice is None


def test_ask_answers_over_an_openai_compatible_server(openai, monkeypatch, tmp_path):
    monkeypatch.setattr(bowerbird.profile, "data_home", lambda: tmp_path)
    conn = db.connect(tmp_path / "test.db")
    conn.execute("INSERT INTO sources(id, kind, browser, profile, path) "
                 "VALUES(1,'chromium','Brave','Test','/tmp/nonexistent')")
    conn.execute("INSERT INTO bookmarks(source_id, guid, title, url, canonical_url, folder_path, root) "
                 "VALUES(1,'g','Bed levelling','https://e.com/bed','https://e.com/bed','Bar','bookmark_bar')")
    conn.execute("INSERT INTO urls(canonical_url, check_url, status) "
                 "VALUES('https://e.com/bed','https://e.com/bed','live')")
    conn.commit()
    categorize.rebuild_index(conn)

    def server(request):
        properties = json.loads(request.content)["response_format"]["json_schema"]["schema"]["properties"]
        if "queries" in properties:
            return completion(json.dumps({"queries": ["bed levelling"]}))
        return completion(json.dumps({"groups": [
            {"theme": "Printing", "items": [{"index": 0, "why": "levels the bed"}]}], "note": ""}))

    openai(server)
    client = TestClient(create_app(tmp_path / "test.db"), base_url="http://127.0.0.1")
    data = client.post("/api/chat", json={"question": "how do I level the bed?"}).json()
    assert data["groups"][0]["items"][0] == {
        "title": "Bed levelling", "url": "https://e.com/bed", "status": "live",
        "topics": None, "why": "levels the bed"}
