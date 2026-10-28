"""AD-10: egress is the only outbound client and accepts only an allow-listed payload. No real network anywhere."""
import ast
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from strydr.egress import (
    NVIDIA_BASE_URL, NVIDIA_DEFAULT_MODEL, EgressError, EgressPayload, OpenAICompatible, RunContextPayload, ProviderConfig, resolve, valid_base_url,
)
from strydr.egress.providers import TIMEOUT_S

PKG = Path(__file__).resolve().parents[1] / "strydr"
HTTP_CLIENTS = {"httpx", "httpx2", "requests", "urllib3", "aiohttp", "http.client", "urllib.request", "websockets", "socket"}

GOOD = dict(rule_id="weekly-ramp", template_id="weekly-ramp", kind="observation", number=32.5, unit="%", units="km",
            when="2 days ago", numbers={"week_distance_m": 30000.0, "events[0].time_s": 1500.0}, terms=["km"],
            reference="Your running this week is 32.5% above your 4-week average.")


def test_only_the_egress_package_imports_an_http_client():
    offenders = []
    for path in PKG.rglob("*.py"):
        if "egress" in path.relative_to(PKG).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            offenders += [f"{path.relative_to(PKG)}: {n}" for n in names if n in HTTP_CLIENTS or n.split(".")[0] in {"httpx", "httpx2", "requests", "urllib3", "aiohttp"}]
    assert offenders == []


def test_payload_accepts_derived_values():
    assert EgressPayload(**GOOD).when == "2 days ago"


@pytest.mark.parametrize("bad", [
    {"lat": 52.37},  # any extra field
    {"source_name": "Synthetic Watch"},
    {"when": "2026-03-03"},  # an exact date
    {"when": "2026-03-03 07:30:00 -0500"},
    {"numbers": {"latitude 52.3": 1.0}},  # keys are plain identifiers
    {"terms": ["Synthetic Watch"]},  # outside the closed vocabulary
    {"reference": "Run started at 52.3700, 4.8900!"},  # coordinates and "!" are outside the allowed characters
    {"reference": "x" * 401},
    {"unit": "Synthetic"},
    {"units": "yards"},
])
def test_payload_rejects_anything_else(bad):
    with pytest.raises(ValidationError):
        EgressPayload(**{**GOOD, **bad})


def _provider(handler) -> OpenAICompatible:
    cfg = ProviderConfig("nvidia", "https://api.example.test/v1", "m", "sk-secret")
    return OpenAICompatible(cfg, transport=httpx.MockTransport(handler))


def test_provider_posts_chat_completions_with_bearer_key_and_the_payload_only():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=json.loads(request.content),
                    timeout=request.extensions["timeout"])
        return httpx.Response(200, json={"choices": [{"message": {"content": " Nice steady week. "}}]})

    out = _provider(handler).complete(EgressPayload(**GOOD), "system rules")
    assert out == "Nice steady week."
    assert seen["url"] == "https://api.example.test/v1/chat/completions" and seen["auth"] == "Bearer sk-secret"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "system rules"}
    assert json.loads(seen["body"]["messages"][1]["content"]) == EgressPayload(**GOOD).model_dump()
    assert seen["timeout"]["read"] == TIMEOUT_S == 20.0 and seen["timeout"]["connect"] == 20.0
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}  # NVIDIA only: answer, don't think


def test_other_providers_get_no_nvidia_only_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(body=json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    cfg = ProviderConfig("openai-compatible", "https://api.example.test/v1", "m", "k")
    OpenAICompatible(cfg, transport=httpx.MockTransport(handler)).complete(EgressPayload(**GOOD), "s")
    assert "chat_template_kwargs" not in seen["body"]


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(500),
    lambda r: httpx.Response(200, json={"unexpected": True}),
    lambda r: httpx.Response(200, content=b"not json"),
    # a reasoning model that spent its budget thinking: no answer, never the text "None"
    lambda r: httpx.Response(200, json={"choices": [{"message": {"content": None, "reasoning_content": "thinking"}}]}),
    lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]}),
])
def test_provider_failures_raise_egress_error_without_leaking(handler):
    with pytest.raises(EgressError) as e:
        _provider(handler).complete(EgressPayload(**GOOD), "s")
    assert "sk-secret" not in str(e.value)


def test_provider_timeout_is_an_egress_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(EgressError):
        _provider(handler).complete(EgressPayload(**GOOD), "s")


def test_provider_refuses_anything_but_an_egress_payload():
    with pytest.raises(TypeError):
        _provider(lambda r: httpx.Response(200)).complete({"lat": 1.0}, "s")


def test_nvidia_is_the_default_and_the_key_stays_out_of_repr():
    cfg = resolve("nvidia", None, None, "sk-secret")
    assert (cfg.base_url, cfg.model) == (NVIDIA_BASE_URL, NVIDIA_DEFAULT_MODEL) == ("https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3.5-lightning-30b-a3b")
    assert "sk-secret" not in repr(cfg)
    with pytest.raises(ValueError):
        resolve("openai-compatible", None, None, "k")
    assert resolve("openai-compatible", "https://x.test/v1", "gpt", "k").model == "gpt"


def test_base_url_must_be_https_unless_local():
    assert valid_base_url("https://integrate.api.nvidia.com/v1") and valid_base_url("http://localhost:11434/v1")
    assert not valid_base_url("http://example.com/v1") and not valid_base_url("https://user:pw@example.com/v1")
    assert not valid_base_url("file:///etc/passwd")


# ---- the run context payload (CAP-16) ----------------------------------------------------------------------------------

RUN_GOOD = dict(units="mi", run={"avg_pace": "14:04 /mi", "when": "today"}, conditions={"temperature": "84\u00b0F", "band": "hot"},
                sleep={"quality": "short"}, splits=[{"split": "1", "pace": "14:04 /mi"}],
                insights=[{"rule_id": "weekly-ramp", "sentence": "Your running this week is 32.5% above your average."}])


def test_run_context_accepts_preformatted_strings():
    assert RunContextPayload(**RUN_GOOD).run["avg_pace"] == "14:04 /mi"


@pytest.mark.parametrize("bad", [
    {"run": {"latitude": "52.3"}},  # an unknown key
    {"run": {"type": "2026-03-03"}},  # a date-shaped value
    {"run": {"type": "7:30 am"}},  # a clock time
    {"run": {"type": "Oct 22"}}, {"run": {"type": "22 October"}},  # a date written with a month name
    {"run": {"distance": "52.123 mi"}},  # coordinate-like decimals
    {"sleep": {"quality": "km"}}, {"run": {"type": "km"}},  # a word outside the key's own set
    {"run": {"type": "run!"}},  # "!"
    {"run": {"type": "x" * 49}},  # too long
    {"run": {"type": ""}},
    {"conditions": {"band": "Synthetic Watch"}},  # not a closed word
    {"sleep": {"quality": "terrible"}},
    {"splits": [{"lat": "1"}]},
    {"insights": [{"rule_id": "Weekly Ramp", "sentence": "ok"}]},
    {"insights": [{"rule_id": "weekly-ramp", "sentence": "Great run!"}]},
    {"insights": [{"rule_id": "weekly-ramp", "sentence": "x"}] * 13},
    {"extra": {}},
    {"units": "yards"},
])
def test_run_context_rejects_anything_else(bad):
    with pytest.raises(ValidationError):
        RunContextPayload(**{**RUN_GOOD, **bad})


def test_provider_posts_a_run_context_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    p = RunContextPayload(**RUN_GOOD)
    assert _provider(handler).complete(p, "s") == "ok"
    assert RunContextPayload.model_validate_json(seen["body"]["messages"][1]["content"]) == p
