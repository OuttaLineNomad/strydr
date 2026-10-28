"""Provider adapters. This package is the only code that imports an HTTP client (AD-2, AD-10)."""
import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from strydr.egress.payload import EgressPayload, RunContextPayload

log = logging.getLogger("strydr.egress")

TIMEOUT_S = 20.0  # AD-5: each AI call times out after 20 s

# Verified 2026-10-26: NVIDIA's hosted catalogue is OpenAI-compatible at this base URL (build.nvidia.com API examples;
# https://docs.openclaw.ai/providers/nvidia lists the free models). The default is a small model NVIDIA serves free.
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
PROVIDERS = ("nvidia", "openai-compatible")


class EgressError(Exception):
    """A provider call failed. Carries a class name only: provider replies and request bodies are never kept."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    model: str
    api_key: str

    def __repr__(self) -> str:  # the key must never reach a log line
        return f"ProviderConfig(provider={self.provider!r}, model={self.model!r})"


def resolve(provider: str, base_url: str | None, model: str | None, api_key: str) -> ProviderConfig:
    if provider == "nvidia":
        return ProviderConfig(provider, base_url or NVIDIA_BASE_URL, model or NVIDIA_DEFAULT_MODEL, api_key)
    if not base_url or not model:
        raise ValueError("an openai-compatible provider needs a base URL and a model")
    return ProviderConfig(provider, base_url, model, api_key)


def valid_base_url(url: str) -> bool:
    u = urlsplit(url)
    local = u.hostname in ("localhost", "127.0.0.1", "::1")
    return bool(u.hostname) and (u.scheme == "https" or (u.scheme == "http" and local)) and not u.username


class Provider(Protocol):
    def complete(self, payload: EgressPayload | RunContextPayload, system: str, max_tokens: int = 120) -> str: ...


class OpenAICompatible:
    """POST {base_url}/chat/completions. `transport` lets tests supply an in-process fake (no network)."""

    def __init__(self, config: ProviderConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self._transport = transport

    def complete(self, payload: EgressPayload | RunContextPayload, system: str, max_tokens: int = 120) -> str:
        if not isinstance(payload, (EgressPayload, RunContextPayload)):  # AD-10: nothing else crosses the boundary
            raise TypeError("egress accepts only an EgressPayload or a RunContextPayload")
        body = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": payload.model_dump_json()}],
            "temperature": 0.3, "max_tokens": max_tokens, "stream": False,
        }
        if self.config.provider == "nvidia":
            # NVIDIA's hosted models default to thinking first, which spends the whole budget on a one-sentence
            # rewording and returns no answer. Rewording needs no reasoning. Verified 2026-10-27.
            body["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            with httpx.Client(timeout=httpx.Timeout(TIMEOUT_S), transport=self._transport) as client:
                r = client.post(self.config.base_url.rstrip("/") + "/chat/completions", json=body,
                                headers={"Authorization": f"Bearer {self.config.api_key}"})
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                # A reasoning model can spend its whole budget thinking and return no answer.
                raise ValueError("empty reply")
            return content.strip()
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
            raise EgressError(type(e).__name__) from None


def make_provider(config: ProviderConfig) -> Provider:
    return OpenAICompatible(config)
