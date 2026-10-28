"""Egress gateway (AD-10): the only module that opens outbound connections."""
from strydr.egress.payload import TERMS, EgressPayload, RunContextPayload
from strydr.egress.providers import (
    NVIDIA_BASE_URL, NVIDIA_DEFAULT_MODEL, PROVIDERS, TIMEOUT_S, EgressError, OpenAICompatible, Provider,
    ProviderConfig, make_provider, resolve, valid_base_url,
)

__all__ = [
    "NVIDIA_BASE_URL", "NVIDIA_DEFAULT_MODEL", "PROVIDERS", "TERMS", "TIMEOUT_S", "EgressError", "EgressPayload", "RunContextPayload",
    "OpenAICompatible", "Provider", "ProviderConfig", "make_provider", "resolve", "valid_base_url",
]
