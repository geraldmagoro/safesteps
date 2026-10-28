"""Meta Model API client (OpenAI-compatible chat completions) + alert triage agent.

Env vars:
  META_API_KEY   required for live calls (never commit it)
  META_API_BASE  optional, default https://api.meta.ai/v1  (check your dashboard)
  META_MODEL     optional, default muse-wonder-1.0
  META_PRICE_IN_PER_M / META_PRICE_OUT_PER_M  optional USD per 1M tokens, used
                 only for the on-screen cost ESTIMATE (defaults 4.0 / 20.0 -
                 confirm against your dashboard).

Design rule: the model ANNOTATES alerts (severity, likely false alarm, plain
language message, a message in the parent's language). It can never suppress or
delay a safety alert - rules fire first, AI enriches afterwards.
"""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from typing import Callable, Dict, List, Optional

MODEL_NAME = os.getenv("META_MODEL", "muse-wonder-1.0")
DEFAULT_BASE = "https://api.meta.ai/v1"
PRICE_IN = float(os.getenv("META_PRICE_IN_PER_M", "4.0"))
PRICE_OUT = float(os.getenv("META_PRICE_OUT_PER_M", "20.0"))

usage: Dict[str, object] = {
    "calls": 0,
    "errors": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "last_latency_s": None,
    "last_error": None,
    "retries": 0,
}


def configured() -> bool:
    return bool(os.getenv("META_API_KEY"))


def endpoint() -> str:
    base = (os.getenv("META_API_BASE") or os.getenv("META_API_URL") or DEFAULT_BASE).rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def status() -> dict:
    cost = (
        usage["prompt_tokens"] * PRICE_IN + usage["completion_tokens"] * PRICE_OUT  # type: ignore[operator]
    ) / 1_000_000
    return {
        "configured": configured(),
        "model": MODEL_NAME,
        "endpoint": endpoint(),
        **usage,
        "est_cost_usd": round(cost, 4),
    }


def chat(messages: List[dict], tools: Optional[List[dict]] = None, timeout: float = 90.0) -> dict:
    """One chat-completions call. Returns the assistant message dict."""
    payload: dict = {"model": MODEL_NAME, "messages": messages}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        endpoint(),
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.getenv('META_API_KEY', '')}",
        },
        method="POST",
    )
    t0 = time.time()
    data: dict = {}
    attempts = max(1, int(os.getenv("META_API_RETRIES", "6")))
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode() or "{}")
            break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            if exc.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                usage["retries"] += 1  # type: ignore[operator]
                time.sleep(min(2 * (attempt + 1), 10))
                continue
            usage["errors"] += 1  # type: ignore[operator]
            usage["last_error"] = f"HTTP {exc.code}: {body}"
            raise RuntimeError(usage["last_error"]) from exc
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as exc:
            # flaky DNS / network (e.g. getaddrinfo failed): wait and try again
            if attempt < attempts - 1:
                usage["retries"] += 1  # type: ignore[operator]
                time.sleep(min(2 * (attempt + 1), 10))
                continue
            usage["errors"] += 1  # type: ignore[operator]
            usage["last_error"] = f"{exc} (after {attempts} attempts)"
            raise RuntimeError(usage["last_error"]) from exc
        except Exception as exc:
            usage["errors"] += 1  # type: ignore[operator]
            usage["last_error"] = str(exc)
            raise
    usage["calls"] += 1  # type: ignore[operator]
    usage["last_latency_s"] = round(time.time() - t0, 2)
    u = data.get("usage") or {}
    usage["prompt_tokens"] += int(u.get("prompt_tokens", 0))  # type: ignore[operator]
    usage["completion_tokens"] += int(u.get("completion_tokens", 0))  # type: ignore[operator]
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        usage["last_error"] = f"unexpected reply shape: {str(data)[:200]}"
        raise RuntimeError(usage["last_error"]) from exc


def selftest() -> dict:
    msg = chat([{"role": "user", "content": "Reply with exactly: SAFESTEPS_OK"}], timeout=60)
    return {"reply": (msg.get("content") or "")[:200], **status()}


# ---------------------------------------------------------- DNS keep-warm
def _warm_loop() -> None:
    """Resolve the API host regularly so a lossy local DNS resolver stays cached."""
    host = urlparse(endpoint()).hostname or "api.meta.ai"
    while True:
        try:
            socket.getaddrinfo(host, 443)
            time.sleep(20)
        except OSError:
            time.sleep(3)  # failed: try again soon


_warmer_started = False


def start_dns_warmer() -> None:
    global _warmer_started
    if _warmer_started or not configured():
        return
    _warmer_started = True
    threading.Thread(target=_warm_loop, name="dns-warm", daemon=True).start()


start_dns_warmer()


# ------------------------------------------------------------------ triage
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_readings",
            "description": "Last N band readings for the child (oldest first): gps, hr, skin gap, link.",
            "parameters": {
                "type": "object",
                "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 30}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_child_profile",
            "description": "Child name, age, school, parent language and emergency contacts count.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_help",
            "description": "Nearest police stations and clinics to the alert location.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM = (
    "You are the triage assistant of SafeSteps, an ankle-band safety system for "
    "children walking to school in South Africa. Deterministic rules have ALREADY "
    "raised this alert and the parent has ALREADY been notified; you cannot cancel "
    "or delay it. Your job is to help the parent act fast and well. Be honest about "
    "uncertainty and never downplay a possible emergency (drowning, faint, band "
    "removed away from school are serious). Use tools if you need history or context. "
    "Finish with ONLY a JSON object with keys: "
    '"severity" (low|medium|high|critical), "confidence" (0-1), '
    '"likely_false_alarm" (boolean), "reasons" (list of up to 3 short strings), '
    '"parent_message" (max 30 words, plain English, tells the parent what to do first), '
    '"parent_message_local" (same message in the requested parent language, or "" if none), '
    '"recommended_action" (one short sentence), "escalate_to_ems" (boolean).'
)


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise ValueError(f"no JSON in model reply: {text[:160]}")


def triage(alert: dict, tool_impls: Dict[str, Callable[..., object]], language: str = "") -> dict:
    """Run the triage agent (blocking; call from a worker thread)."""
    lang = language.strip() or "none"
    user = (
        f"ALERT: {json.dumps({k: alert.get(k) for k in ('type', 'detail', 'location', 'timestamp', 'link', 'delivery_delay_s')})}\n"
        f"Requested parent language for parent_message_local: {lang}.\n"
        "Assess it now."
    )
    messages: List[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]
    for _ in range(4):  # at most 3 tool rounds + final answer
        msg = chat(messages, tools=TOOLS)
        calls = msg.get("tool_calls") or []
        if not calls:
            out = _extract_json(msg.get("content") or "")
            out["model"] = MODEL_NAME
            return out
        messages.append(
            {"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls}
        )
        for c in calls:
            fn = c.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            impl = tool_impls.get(name)
            try:
                result = impl(**args) if impl else {"error": f"unknown tool {name}"}
            except Exception as exc:
                result = {"error": str(exc)}
            messages.append(
                {"role": "tool", "tool_call_id": c.get("id", ""), "content": json.dumps(result)}
            )
    raise RuntimeError("triage did not finish within the tool-round limit")
