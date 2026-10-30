"""Meta Model client: retries on flaky networks, parses model output, runs tool calls."""
import json
import urllib.error

import pytest

from backend import ai


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._p).encode()


def _ok(content="SAFESTEPS_OK"):
    return {"choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7}}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-key")
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)
    for k in ("calls", "errors", "retries", "prompt_tokens", "completion_tokens"):
        ai.usage[k] = 0
    ai.usage["last_error"] = None


def test_retries_on_dns_failure_then_succeeds(monkeypatch):
    n = {"i": 0}

    def fake(req, timeout=0):
        n["i"] += 1
        if n["i"] < 3:
            raise urllib.error.URLError(OSError(11001, "getaddrinfo failed"))
        return _Resp(_ok())

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake)
    msg = ai.chat([{"role": "user", "content": "x"}])
    assert msg["content"] == "SAFESTEPS_OK"
    assert ai.usage["retries"] == 2 and ai.usage["calls"] == 1 and ai.usage["errors"] == 0
    assert ai.usage["last_error"] is None  # a later success clears the stale error


def test_gives_up_cleanly_after_all_retries(monkeypatch):
    def fake(req, timeout=0):
        raise urllib.error.URLError(OSError(11001, "getaddrinfo failed"))

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake)
    with pytest.raises(RuntimeError, match="attempts"):
        ai.chat([{"role": "user", "content": "x"}])
    assert ai.usage["errors"] == 1


def test_client_error_is_not_retried(monkeypatch):
    n = {"i": 0}

    def fake(req, timeout=0):
        n["i"] += 1
        raise urllib.error.HTTPError("u", 401, "unauthorized", {}, None)

    monkeypatch.setattr(ai.urllib.request, "urlopen", fake)
    with pytest.raises(RuntimeError, match="401"):
        ai.chat([{"role": "user", "content": "x"}])
    assert n["i"] == 1


def test_extract_json_from_fenced_reply():
    out = ai._extract_json("Sure!\n```json\n{\"severity\": \"high\"}\n```")
    assert out == {"severity": "high"}


def test_triage_runs_tool_then_returns_structured_result(monkeypatch):
    calls = {"tool": 0}
    scripted = [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "get_child_profile", "arguments": "{}"}}]},
        {"role": "assistant", "content": "```json\n" + json.dumps({
            "severity": "high", "confidence": 0.7, "likely_false_alarm": False, "reasons": ["a"],
            "parent_message": "Call now", "parent_message_local": "", "recommended_action": "Call",
            "escalate_to_ems": False}) + "\n```"},
    ]
    seen = []

    def fake_chat(messages, tools=None, timeout=90.0):
        seen.append(messages)
        return scripted.pop(0)

    def get_child_profile():
        calls["tool"] += 1
        return {"name": "Naledi"}

    monkeypatch.setattr(ai, "chat", fake_chat)
    out = ai.triage({"type": "skin_off", "detail": "x"}, {"get_child_profile": get_child_profile}, "isiZulu")
    assert out["severity"] == "high" and out["model"] == ai.MODEL_NAME
    assert calls["tool"] == 1
    assert any(m["role"] == "tool" for m in seen[-1])  # the tool result went back to the model


def test_unknown_tool_does_not_crash_triage(monkeypatch):
    scripted = [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "launch_missiles", "arguments": "{}"}}]},
        {"role": "assistant", "content": "{\"severity\": \"low\"}"},
    ]
    monkeypatch.setattr(ai, "chat", lambda m, tools=None, timeout=90.0: scripted.pop(0))
    assert ai.triage({"type": "x"}, {}, "")["severity"] == "low"
