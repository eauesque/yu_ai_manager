from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictStr

from core.infra_core.api_models import ApiModel


class DiscoveredCandidateRequest(ApiModel):
    provider: Literal["ollama", "openai_compat", "hailo_genai"]
    base_url: StrictStr = Field(min_length=1)


class RegisterDiscoveredCandidateRequest(DiscoveredCandidateRequest):
    name: StrictStr | None = None
    model: StrictStr | None = None
    model_name: StrictStr | None = None
    api_key: StrictStr | None = None


class TestDiscoveredCandidateRequest(RegisterDiscoveredCandidateRequest):
    pass


class MatchDiscoveredCandidateRequest(DiscoveredCandidateRequest):
    server_id: StrictStr = Field(min_length=1)


class IgnoreDiscoveredCandidateRequest(ApiModel):
    base_url: StrictStr = Field(min_length=1)
