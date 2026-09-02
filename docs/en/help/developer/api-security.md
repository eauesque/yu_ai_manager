# API Security Guidelines

Use this document whenever you add or change an API endpoint.

## First decision

Every endpoint must be classified up front as one of:

- `public`
- `session/user`
- `admin`
- `localhost-only`

If unsure, choose `admin`.

## Core rules

1. Do not assume `GET` is safe.
2. `read-only API keys` are for thin reads only.
3. Internal paths, inventories, history, content, logs, and analysis results are `admin`.
4. Localhost checks must use proxy-aware helpers.
5. Config endpoints require allowlists and strict validation.
6. Secrets must be encrypted and redacted through shared helpers.

## Not safe for read-only keys

- internal paths
- file/member ID inventories
- prompts, annotations, transcripts, chat logs
- OCR / analysis results
- queue, history, audit, approval, scheduler, scan error state
- extension / profile / backup / webhook / secret backend state
- results fetched with stored third-party credentials

## Localhost checks

Do not use raw:

- `request.remote_addr == "127.0.0.1"`

Use existing helpers instead:

- `get_client_ip()`
- `is_local_request()`
- `is_loopback_request()`

## Config endpoint rules

Required:

- key allowlist
- strict type validation
- range / enum / URL validation
- secret redaction on reads
- encrypted storage for secrets

Forbidden:

- blind `config.update(...)`
- `bool(value)` for request booleans
- generic merges that bypass secret handling

## Secrets

- never return current secret values
- never include tokens/headers/secret blobs in list endpoints
- never overwrite existing secrets with masked placeholders
- always use a dedicated store or shared helper

## Outbound requests from APIs

Do not make upstream probes or discovery fetches from `GET` endpoints.

If unavoidable:

- require `admin`
- keep timeouts short
- block localhost / private IP / metadata targets

## Minimum tests

For sensitive endpoints, add:

1. `read-only key -> 403`
2. `admin key -> 200`
3. invalid input -> `400`
4. secret redaction checks
5. proxy-aware localhost regression tests where relevant

## Review checklist

- Is this `GET` really safe for public/read-only access?
- Does it expose paths, inventories, prompts, transcripts, history, or raw metadata?
- Does it leak secrets?
- Does it use proxy-aware helpers?
- Does it avoid implicit boolean coercion?
- Does it avoid blind config merges?
- Does it avoid unintended outbound requests?
- Does it include admin-scope regression tests?

Default policy: start narrow, then open deliberately only when needed.
