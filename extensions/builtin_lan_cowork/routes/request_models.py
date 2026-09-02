from __future__ import annotations

import base64
import binascii
from typing import Annotated, Any, Literal

from pydantic import (
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from core.infra_core.api_models import ApiModel, FileId

PeerFiniteNumber = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]


class LanCoworkFlexibleApiModel(ApiModel):
    model_config = ConfigDict(
        extra="allow",
        allow_inf_nan=False,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ClientPairRequest(ApiModel):
    peer_id: StrictStr = Field(min_length=1)


class ClientPairVerifyRequest(ApiModel):
    peer_id: StrictStr = Field(min_length=1)
    request_id: StrictStr = Field(min_length=1)
    pin: StrictStr = Field(min_length=1)


class PeerPairRequest(ApiModel):
    peer_id: StrictStr = Field(min_length=1)
    host: StrictStr = Field(min_length=1)
    port: StrictInt = Field(ge=1, le=65535)
    pubkey: StrictStr = Field(min_length=1)
    x25519_pk: StrictStr | None = None
    commit: StrictStr = Field(min_length=1)


class PairRequestId(ApiModel):
    request_id: StrictStr = Field(min_length=1)


class PairVerifyRequest(ApiModel):
    request_id: StrictStr = Field(min_length=1)
    encrypted_bundle: StrictStr = Field(min_length=1)


class PeerRegisterRequest(ApiModel):
    host: StrictStr = Field(min_length=1)
    port: StrictInt = Field(default=5000, ge=1, le=65535)


class PeerHeartbeatRequest(ApiModel):
    generating: StrictBool | None = None
    queue_depth: StrictInt | None = None
    bridges: list[str] | None = None
    inference_types: list[str] | None = None


class PeerEventRequest(ApiModel):
    event_type: StrictStr = Field(min_length=1, max_length=128)
    event_data: dict[str, Any] = Field(default_factory=dict)
    source_peer: StrictStr = ""


class LocalImportSessionCreateRequest(ApiModel):
    peer_id: StrictStr = Field(min_length=1)
    peer_name: StrictStr = ""
    mode: Literal["full", "diff", "selective"] = "full"
    import_folder: StrictStr = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class LocalImportExecuteRequest(ApiModel):
    session_id: StrictStr = Field(min_length=1)
    file_ids: list[FileId] | None = None


class LocalImportIndexRequest(ApiModel):
    peer_id: StrictStr = Field(min_length=1)
    import_folder: StrictStr = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class PeerAuthSettingsUpdateRequest(ApiModel):
    protect_heartbeat: StrictBool | None = None
    protect_events: StrictBool | None = None
    allowed_cidr: StrictInt | None = Field(default=None, ge=8, le=32)

    @model_validator(mode="after")
    def _require_any_field(self) -> PeerAuthSettingsUpdateRequest:
        if all(
            getattr(self, field_name) is None
            for field_name in (
                "protect_heartbeat",
                "protect_events",
                "allowed_cidr",
            )
        ):
            raise ValueError("no valid fields provided")
        return self


class FleetSettingsUpdateRequest(ApiModel):
    chief: StrictBool


class FleetAllowlistsUpdateRequest(ApiModel):
    allow_log_stream_from: list[Any] | None = None
    allow_update_from: list[Any] | None = None
    allow_restart_from: list[Any] | None = None
    # NOTE: allow_remote_update is historically named for "update" but acts as
    # the master switch for ALL fleet operations (restart, update, log stream).
    allow_remote_update: StrictBool | None = None

    @model_validator(mode="after")
    def _require_any_field(self) -> FleetAllowlistsUpdateRequest:
        if (
            self.allow_log_stream_from is None
            and self.allow_update_from is None
            and self.allow_restart_from is None
            and self.allow_remote_update is None
        ):
            raise ValueError("no valid fields provided")
        return self


class PeerCharacterCenterRequest(LanCoworkFlexibleApiModel):
    x: PeerFiniteNumber
    y: PeerFiniteNumber


class PeerCharacterRequest(LanCoworkFlexibleApiModel):
    prompt: StrictStr = ""
    negative: StrictStr = ""
    center: PeerCharacterCenterRequest | None = None


class PeerReferenceImageRequest(LanCoworkFlexibleApiModel):
    image: StrictStr = ""
    type: StrictStr = "character_and_style"
    information_extracted: PeerFiniteNumber = 1.0
    strength: PeerFiniteNumber = 1.0


class PeerLoraRequest(LanCoworkFlexibleApiModel):
    name: StrictStr = ""
    strength_model: PeerFiniteNumber = 1.0
    strength_clip: PeerFiniteNumber = 1.0


class PeerGenerationRequest(LanCoworkFlexibleApiModel):
    # Wire format: bridge generation parameters (seed/cfg/steps/sampler_name/
    # width/height/sweep_meta/...) are sent as TOP-LEVEL flat fields. The 3
    # Bridge JS clients only know flat-shape, and GenJob.to_dict() spreads
    # params at the top level too. extra="allow" (via LanCoworkFlexibleApiModel)
    # absorbs them; GenJob.from_dict folds them into job.params for the
    # receiver's **job.params expansion. Legacy nested {"params": {...}} is
    # still accepted for back-compat (model_dump preserves it as an extra,
    # and from_dict merges it before overlaying flat extras).
    bridge: StrictStr = Field(min_length=1)
    prompt: StrictStr | None = ""
    negative_prompt: StrictStr | None = ""
    job_id: StrictStr | None = ""
    source_peer: StrictStr | None = ""
    target_peer: StrictStr | None = ""
    status: StrictStr | None = "pending"
    image_sync: StrictStr | None = "immediate"
    error: StrictStr | None = ""
    elapsed_ms: PeerFiniteNumber | None = 0
    expanded_prompt: StrictStr | None = ""

    model: StrictStr | None = None
    sampler: StrictStr | None = None
    sampler_name: StrictStr | None = None
    noise_schedule: StrictStr | None = None
    image_format: StrictStr | None = None
    image: StrictStr | None = None
    mask: StrictStr | None = None
    reference_image: StrictStr | None = None
    hr_upscaler: StrictStr | None = None
    refiner_checkpoint: StrictStr | None = None
    mode: StrictStr | None = None
    ckpt_name: StrictStr | None = None
    diffusion_model: StrictStr | None = None
    vae_name: StrictStr | None = None
    text_encoder_1: StrictStr | None = None
    text_encoder_2: StrictStr | None = None
    clip_type: StrictStr | None = None
    weight_dtype: StrictStr | None = None
    controlnet_model: StrictStr | None = None
    controlnet_image_name: StrictStr | None = None
    upscale_model: StrictStr | None = None
    scheduler: StrictStr | None = None
    image_base64: StrictStr | None = None
    task_id: StrictStr | None = None
    backend_id: StrictStr | None = None

    steps: PeerFiniteNumber | None = None
    width: PeerFiniteNumber | None = None
    height: PeerFiniteNumber | None = None
    seed: PeerFiniteNumber | None = None
    n_samples: PeerFiniteNumber | None = None
    uc_preset: PeerFiniteNumber | None = None
    batch_count: PeerFiniteNumber | None = None
    batch_size: PeerFiniteNumber | None = None
    hr_second_pass_steps: PeerFiniteNumber | None = None
    hr_resize_x: PeerFiniteNumber | None = None
    hr_resize_y: PeerFiniteNumber | None = None
    scale: PeerFiniteNumber | None = None
    cfg: PeerFiniteNumber | None = None
    cfg_scale: PeerFiniteNumber | None = None
    cfg_rescale: PeerFiniteNumber | None = None
    uncond_scale: PeerFiniteNumber | None = None
    strength: PeerFiniteNumber | None = None
    noise: PeerFiniteNumber | None = None
    reference_strength: PeerFiniteNumber | None = None
    reference_information_extracted: PeerFiniteNumber | None = None
    hr_scale: PeerFiniteNumber | None = None
    denoising_strength: PeerFiniteNumber | None = None
    denoise: PeerFiniteNumber | None = None
    refiner_switch_at: PeerFiniteNumber | None = None
    controlnet_strength: PeerFiniteNumber | None = None

    characters: list[PeerCharacterRequest] | None = None
    reference_image_multiple: list[PeerReferenceImageRequest] | None = None
    loras: list[PeerLoraRequest] | None = None
    init_images: list[StrictStr] | None = None


class PeerProgressCancelRequest(LanCoworkFlexibleApiModel):
    bridge: StrictStr = Field(min_length=1)
    source_peer: StrictStr = ""
    target_peer: StrictStr = ""
    task_id: StrictStr | None = None


class PeerLlmChatRequest(ApiModel):
    messages: list[dict[str, Any]] = Field(min_length=1)
    max_tokens: StrictInt = Field(default=256, ge=1)
    temperature: StrictFloat | StrictInt = 0.7


class PeerSyncPushRequest(ApiModel):
    path: StrictStr = Field(min_length=1)
    content_b64: StrictStr = Field(min_length=1)

    @field_validator("content_b64")
    @classmethod
    def _validate_content_b64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("content_b64 must be valid base64") from exc
        return value


class PeerSyncNotifyRequest(ApiModel):
    path: StrictStr = Field(min_length=1)
    peer_id: StrictStr = ""


class PeerNegotiateRequest(LanCoworkFlexibleApiModel):
    task_type: StrictStr = Field(min_length=1)
    proposal_id: StrictStr = ""
    requirements: dict[str, Any] | None = None
