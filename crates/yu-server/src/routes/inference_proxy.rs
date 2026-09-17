use axum::{
    body::{to_bytes, Body},
    extract::State,
    http::{header, HeaderValue, Request, StatusCode, Uri},
    response::{IntoResponse, Response},
    Json,
};

use crate::state::SharedState;

const INFERENCE_BASE_URL: &str = "http://localhost:5001";
const INFERENCE_PREFIX: &str = "/api/inference";

pub async fn proxy(State(state): State<SharedState>, request: Request<Body>) -> Response {
    let (parts, body) = request.into_parts();
    let target_url = proxy_target_url(&parts.uri);
    let body = match to_bytes(body, 100 * 1024 * 1024).await {
        Ok(body) => body,
        Err(error) => {
            tracing::error!(?error, "failed to read inference proxy request body");
            return inference_service_unavailable();
        }
    };

    let mut builder = state
        .inference_client
        .request(parts.method, target_url)
        .body(body);

    for (name, value) in parts.headers {
        let Some(name) = name else {
            continue;
        };
        if should_forward_request_header(&name) {
            builder = builder.header(name, value);
        }
    }

    let upstream = match builder.send().await {
        Ok(response) => response,
        Err(error) => {
            tracing::error!(?error, "inference service unavailable");
            return inference_service_unavailable();
        }
    };

    let status = upstream.status();
    let headers = upstream.headers().clone();
    let is_sse = headers
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|ct| ct.starts_with("text/event-stream"));
    let stream = upstream.bytes_stream();

    let mut response = Response::builder().status(status);
    let response_headers = response.headers_mut().expect("response builder is valid");
    for (name, value) in headers {
        let Some(name) = name else {
            continue;
        };
        response_headers.insert(name, value);
    }
    if is_sse {
        response_headers.insert("x-accel-buffering", HeaderValue::from_static("no"));
    }

    response
        .body(Body::from_stream(stream))
        .unwrap_or_else(|error| {
            tracing::error!(?error, "failed to build inference proxy response");
            inference_service_unavailable()
        })
}

fn should_forward_request_header(name: &header::HeaderName) -> bool {
    *name != header::CONTENT_TYPE && *name != header::CONTENT_LENGTH && *name != header::HOST
}

fn proxy_target_url(uri: &Uri) -> String {
    let path_and_query = uri.path_and_query().map_or("/", |value| value.as_str());
    let suffix = path_and_query
        .strip_prefix(INFERENCE_PREFIX)
        .unwrap_or(path_and_query);
    let suffix = if suffix.is_empty() { "/" } else { suffix };
    format!("{INFERENCE_BASE_URL}{suffix}")
}

fn inference_service_unavailable() -> Response {
    (
        StatusCode::BAD_GATEWAY,
        Json(serde_json::json!({
            "error": "inference_service_unavailable",
        })),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn proxy_builds_correct_url() {
        let uri = "/api/inference/v1/images:tag?limit=10"
            .parse::<Uri>()
            .unwrap();

        assert_eq!(
            proxy_target_url(&uri),
            "http://localhost:5001/v1/images:tag?limit=10"
        );

        let uri = "/api/inference".parse::<Uri>().unwrap();
        assert_eq!(proxy_target_url(&uri), "http://localhost:5001/");
    }
}
