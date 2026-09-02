use serde_json::json;

use infer_core::yolo_postprocess::Detection;

/// Default `timeout_ms` for LLM/VLM generate calls when the caller doesn't
/// override it. yu-infer's own default (30s) is tuned for a healthy device;
/// under low `CmaFree` a cold model load alone can take 60-100s+ even though
/// the request eventually succeeds (measured on real Hailo-10H hardware,
/// TODO.md "低 CmaFree 下では...HAILO_TIMEOUT"), so 30s spuriously surfaces
/// HAILO_TIMEOUT for requests that would otherwise complete fine.
pub const DEFAULT_GENERATE_TIMEOUT_MS: u32 = 120_000;

#[derive(Clone)]
pub struct InferClient {
    base_url: String,
    auth_token: String,
    http: reqwest::Client,
}

/// One transcribed segment, matching yu-infer's `{"text","start","end"}`
/// response shape (mirrors the SDK's `Speech2Text::SegmentInfo`).
#[derive(Debug, Clone, serde::Deserialize, Default)]
pub struct S2tSegment {
    pub text: String,
    pub start: f32,
    pub end: f32,
}

#[derive(Debug, Clone, Default)]
pub struct S2tTranscription {
    pub text: String,
    pub segments: Vec<S2tSegment>,
}

#[derive(Debug, thiserror::Error)]
pub enum InferClientError {
    #[error("request failed: {0}")]
    Request(#[from] reqwest::Error),
    #[error("yu-infer returned status {status}: {body}")]
    BadStatus { status: u16, body: String },
    #[error("invalid yu-infer YOLO response: {0}")]
    InvalidYoloResponse(String),
    #[error("invalid yu-infer response: {0}")]
    InvalidResponse(String),
}

impl InferClient {
    pub fn new(base_url: String, auth_token: String) -> Self {
        Self {
            base_url,
            auth_token,
            http: reqwest::Client::new(),
        }
    }

    fn endpoint(&self, path: &str) -> String {
        format!("{}{}", self.base_url, path)
    }

    pub async fn infer_wd(
        &self,
        path: &str,
        model_id: &str,
        general_thr: f32,
        character_thr: f32,
        profile: Option<&serde_json::Value>,
        model_subdir: Option<&str>,
    ) -> Result<serde_json::Value, InferClientError> {
        let mut payload = json!({
            "path": path,
            "model_id": model_id,
            "general_thr": general_thr,
            "character_thr": character_thr,
        });
        if let Some(profile) = profile {
            payload["profile"] = profile.clone();
        }
        if let Some(subdir) = model_subdir.filter(|s| !s.is_empty()) {
            payload["model_subdir"] = json!(subdir);
        }
        let response = self
            .http
            .post(format!("{}/v1/infer/wd", self.base_url))
            .bearer_auth(&self.auth_token)
            .json(&payload)
            .send()
            .await?;

        self.json_response(response).await
    }

    /// Encode a JPEG/PNG image with yu-infer's Hailo CLIP image encoder.
    pub async fn infer_clip_image(
        &self,
        image_base64: String,
    ) -> Result<serde_json::Value, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/clip-image"))
            .bearer_auth(&self.auth_token)
            .json(&json!({"image_base64": image_base64}))
            .send()
            .await?;
        self.json_response(response).await
    }

    /// Encode text with yu-infer's ONNX CLIP text encoder.
    pub async fn infer_clip_text(
        &self,
        text: String,
    ) -> Result<serde_json::Value, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/clip-text"))
            .bearer_auth(&self.auth_token)
            .json(&json!({"text": text}))
            .send()
            .await?;
        self.json_response(response).await
    }

    pub async fn infer_yolo_metadata(
        &self,
        hef_path: Option<String>,
    ) -> Result<serde_json::Value, InferClientError> {
        let request = self
            .http
            .get(self.endpoint("/v1/infer/yolo/metadata"))
            .bearer_auth(&self.auth_token);

        self.send_optional_hef_query(request, hef_path).await
    }

    pub async fn infer_yolo_smoke_zero(
        &self,
        hef_path: Option<String>,
    ) -> Result<serde_json::Value, InferClientError> {
        let request = self
            .http
            .get(self.endpoint("/v1/infer/yolo/smoke-zero"))
            .bearer_auth(&self.auth_token);

        self.send_optional_hef_query(request, hef_path).await
    }

    pub async fn infer_yolo_detect(
        &self,
        hef_path: Option<String>,
        input_base64: String,
        conf_threshold: f64,
        iou_threshold: f64,
        num_classes: usize,
        input_size: u32,
        orig_w: u32,
        orig_h: u32,
        scale: f64,
        pad_x: f64,
        pad_y: f64,
    ) -> Result<Vec<Detection>, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/yolo/detect"))
            .bearer_auth(&self.auth_token)
            .json(&json!({
                "hef_path": hef_path,
                "input_base64": input_base64,
                "conf_threshold": conf_threshold,
                "iou_threshold": iou_threshold,
                "num_classes": num_classes,
                "input_size": input_size,
                "orig_w": orig_w,
                "orig_h": orig_h,
                "scale": scale,
                "pad_x": pad_x,
                "pad_y": pad_y,
            }))
            .send()
            .await?;
        let response = self.json_response(response).await?;
        let data = response.get("data").unwrap_or(&response);
        let detections = data
            .get("detections")
            .ok_or_else(|| InferClientError::InvalidYoloResponse("missing detections".to_string()))?
            .clone();
        serde_json::from_value(detections)
            .map_err(|error| InferClientError::InvalidYoloResponse(error.to_string()))
    }

    pub async fn speech2text_tokenize(
        &self,
        hef_path: Option<String>,
        text: String,
    ) -> Result<serde_json::Value, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/speech2text/tokenize"))
            .bearer_auth(&self.auth_token)
            .json(&json!({
                "hef_path": hef_path,
                "text": text,
            }))
            .send()
            .await?;

        self.json_response(response).await
    }

    /// Transcribes 16 kHz mono WAV audio (already base64-encoded by the
    /// caller) via yu-infer's `/v1/infer/speech2text/transcribe`, which
    /// itself decodes/resamples the WAV -- callers do not need to touch PCM
    /// samples directly.
    pub async fn speech2text_transcribe(
        &self,
        hef_path: Option<String>,
        audio_base64: String,
        language: Option<String>,
        timeout_ms: u32,
    ) -> Result<S2tTranscription, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/speech2text/transcribe"))
            .bearer_auth(&self.auth_token)
            .json(&json!({
                "hef_path": hef_path,
                "audio_base64": audio_base64,
                "language": language,
                "timeout_ms": timeout_ms,
            }))
            .send()
            .await?;
        let value = self.json_response(response).await?;
        let data = value.get("data").unwrap_or(&value);
        let text = data
            .get("text")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default()
            .to_string();
        let segments = data
            .get("segments")
            .cloned()
            .map(serde_json::from_value)
            .transpose()
            .map_err(|error: serde_json::Error| {
                InferClientError::InvalidResponse(format!("malformed segments: {error}"))
            })?
            .unwrap_or_default();
        Ok(S2tTranscription { text, segments })
    }

    pub async fn llm_tokenize(
        &self,
        hef_path: Option<String>,
        text: String,
    ) -> Result<serde_json::Value, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/llm/tokenize"))
            .bearer_auth(&self.auth_token)
            .json(&json!({
                "hef_path": hef_path,
                "text": text,
            }))
            .send()
            .await?;

        self.json_response(response).await
    }

    pub async fn llm_generate(
        &self,
        hef_path: Option<String>,
        prompt: String,
        timeout_ms: Option<u32>,
    ) -> Result<serde_json::Value, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/llm/generate"))
            .bearer_auth(&self.auth_token)
            .json(&json!({
                "hef_path": hef_path,
                "prompt": prompt,
                "timeout_ms": timeout_ms,
            }))
            .send()
            .await?;

        self.json_response(response).await
    }

    pub async fn vlm_generate(
        &self,
        hef_path: String,
        prompt: String,
        frames: Vec<String>,
        timeout_ms: u32,
    ) -> Result<String, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/vlm/generate"))
            .bearer_auth(&self.auth_token)
            .json(&json!({
                "hef_path": hef_path,
                "prompt": prompt,
                "frames": frames,
                "timeout_ms": timeout_ms,
            }))
            .send()
            .await?;
        self.json_response(response)
            .await?
            .get("data")
            .and_then(|data| data.get("text"))
            .and_then(serde_json::Value::as_str)
            .map(str::to_owned)
            .ok_or_else(|| InferClientError::InvalidResponse("missing data.text".to_string()))
    }

    /// Starts an LLM streaming generation and returns the raw upstream
    /// response (a `text/event-stream` body from `yu-infer`) for the caller
    /// to re-stream to its own client. `messages` is an ordered chat history
    /// (`[{"role": ..., "content": ...}, ...]`) — yu-infer's LLM streaming
    /// endpoint is per-request stateless, so the full conversation must be
    /// resent on every turn. `tools` is a list of OpenAI-function-style tool
    /// definitions, forwarded to HailoRT's native `write(messages, tools)` so
    /// the model's own chat template renders them (empty means no tools).
    #[allow(clippy::too_many_arguments)]
    pub async fn llm_generate_stream(
        &self,
        hef_path: Option<String>,
        messages: Vec<serde_json::Value>,
        tools: Vec<serde_json::Value>,
        timeout_ms: Option<u32>,
        temperature: Option<f32>,
        top_p: Option<f32>,
        top_k: Option<u32>,
        frequency_penalty: Option<f32>,
        max_generated_tokens: Option<u32>,
        do_sample: Option<bool>,
        seed: Option<u32>,
    ) -> Result<reqwest::Response, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/llm/generate/stream"))
            .bearer_auth(&self.auth_token)
            .json(&json!({
                "hef_path": hef_path,
                "messages": messages,
                "tools": tools,
                "timeout_ms": timeout_ms,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "frequency_penalty": frequency_penalty,
                "max_generated_tokens": max_generated_tokens,
                "do_sample": do_sample,
                "seed": seed,
            }))
            .send()
            .await?;

        let status = response.status();
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(InferClientError::BadStatus {
                status: status.as_u16(),
                body,
            });
        }
        Ok(response)
    }

    /// Starts a VLM streaming generation and returns the raw upstream
    /// response (a `text/event-stream` body from `yu-infer`) for the caller
    /// to re-stream to its own client.
    #[allow(clippy::too_many_arguments)]
    pub async fn vlm_generate_stream(
        &self,
        hef_path: Option<String>,
        prompt: String,
        system_prompt: Option<String>,
        frames: Vec<String>,
        timeout_ms: Option<u32>,
        temperature: Option<f32>,
        top_p: Option<f32>,
        top_k: Option<u32>,
        frequency_penalty: Option<f32>,
        max_generated_tokens: Option<u32>,
        do_sample: Option<bool>,
        seed: Option<u32>,
    ) -> Result<reqwest::Response, InferClientError> {
        let response = self
            .http
            .post(self.endpoint("/v1/infer/vlm/generate/stream"))
            .bearer_auth(&self.auth_token)
            .json(&json!({
                "hef_path": hef_path,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "frames": frames,
                "timeout_ms": timeout_ms,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "frequency_penalty": frequency_penalty,
                "max_generated_tokens": max_generated_tokens,
                "do_sample": do_sample,
                "seed": seed,
            }))
            .send()
            .await?;

        let status = response.status();
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(InferClientError::BadStatus {
                status: status.as_u16(),
                body,
            });
        }
        Ok(response)
    }

    /// `generation` is a monotonically increasing counter from the caller,
    /// assigned in write order. The pinned `yu-hailo-infer` handler
    /// (`_internal/scan-roots-changed`) remembers the highest generation it
    /// applied and drops anything not strictly newer, so a request the caller
    /// gave up on cannot land late and clobber a newer one; see the call site
    /// in `routes/scan_roots.rs` for why that can happen even with the
    /// caller's own send ordering.
    pub async fn scan_roots_changed(
        &self,
        scan_roots: &[String],
        generation: u64,
    ) -> Result<serde_json::Value, InferClientError> {
        let response = self
            .http
            .post(format!("{}/_internal/scan-roots-changed", self.base_url))
            .bearer_auth(&self.auth_token)
            .json(&json!({ "scan_roots": scan_roots, "generation": generation }))
            .send()
            .await?;

        self.json_response(response).await
    }

    async fn send_optional_hef_query(
        &self,
        mut request: reqwest::RequestBuilder,
        hef_path: Option<String>,
    ) -> Result<serde_json::Value, InferClientError> {
        if let Some(hef_path) = hef_path {
            request = request.query(&[("hef_path", hef_path)]);
        }
        self.json_response(request.send().await?).await
    }

    async fn json_response(
        &self,
        response: reqwest::Response,
    ) -> Result<serde_json::Value, InferClientError> {
        let status = response.status();
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(InferClientError::BadStatus {
                status: status.as_u16(),
                body,
            });
        }

        Ok(response.json().await?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hailo_endpoints_match_yu_infer_routes() {
        let client = InferClient::new("http://127.0.0.1:18771".to_string(), "secret".to_string());

        assert_eq!(
            client.endpoint("/v1/infer/yolo/metadata"),
            "http://127.0.0.1:18771/v1/infer/yolo/metadata"
        );
        assert_eq!(
            client.endpoint("/v1/infer/yolo/smoke-zero"),
            "http://127.0.0.1:18771/v1/infer/yolo/smoke-zero"
        );
        assert_eq!(
            client.endpoint("/v1/infer/yolo/detect"),
            "http://127.0.0.1:18771/v1/infer/yolo/detect"
        );
        assert_eq!(
            client.endpoint("/v1/infer/clip-image"),
            "http://127.0.0.1:18771/v1/infer/clip-image"
        );
        assert_eq!(
            client.endpoint("/v1/infer/clip-text"),
            "http://127.0.0.1:18771/v1/infer/clip-text"
        );
        assert_eq!(
            client.endpoint("/v1/infer/speech2text/tokenize"),
            "http://127.0.0.1:18771/v1/infer/speech2text/tokenize"
        );
        assert_eq!(
            client.endpoint("/v1/infer/llm/tokenize"),
            "http://127.0.0.1:18771/v1/infer/llm/tokenize"
        );
        assert_eq!(
            client.endpoint("/v1/infer/llm/generate"),
            "http://127.0.0.1:18771/v1/infer/llm/generate"
        );
        assert_eq!(
            client.endpoint("/v1/infer/vlm/generate/stream"),
            "http://127.0.0.1:18771/v1/infer/vlm/generate/stream"
        );
        assert_eq!(
            client.endpoint("/v1/infer/llm/generate/stream"),
            "http://127.0.0.1:18771/v1/infer/llm/generate/stream"
        );
    }
}
