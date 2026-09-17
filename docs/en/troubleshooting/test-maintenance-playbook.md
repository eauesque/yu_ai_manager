# Test Maintenance Playbook

A guide to key points when pytest gets stuck due to outdated test infrastructure or environment dependencies.

## Purpose

- Distinguish between `failed` and `skipped` tests
- Differentiate between normal environment-dependent skips and stale tests that need repair
- Establish a fixed shortest path when a broad run (`pytest tests -q --maxfail=1`) gets stuck

## Basic Commands

Normal full check:

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

Also check skip reasons:

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

Treat shared test server strictly:

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

License audit:

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## Reading Current Skips

As of 2026-04-21, broad runs show that skip reasons are concentrated in these 5 main categories.

### 1. Shared Test Server Not Started

The most common skip. The shared server in `tests/conftest.py` uses best-effort startup, and if startup fails, browser / server-dependent groups are dropped to skip rather than fail.

Representative reasons:

- `Shared test server unavailable on port <PORT>`

Main targets:

- `tests/api/`
- Browser UX review suites
- LAN Cowork / Fleet browser/server-dependent tests
- Live browser tests using `TARGET_URL` / `BASE` / `TARGET`
- Audit tests using custom Playwright/WebKit fixtures instead of the `page` fixture

In a normal run, this is a **normal skip**. However, investigate if:

- Unit tests unrelated to the shared server are also being skipped for the same reason
- Previously passing shared server tests suddenly start skipping in large numbers
- The cause is unclear even with `PYTEST_STRICT_AUTOSTART_SERVER=1`

### 2. OS-Specific Tests

Linux-specific sandbox / AppArmor / process isolation suites. Skipping is correct on Windows.

Representative examples:

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

Representative reasons:

- `Linux only`
- `AppArmor is Linux-specific`

This is a **normal skip**.

### 3. Optional Dependencies and Missing External Components

Tests that don't run in environments without specific packages or external nodes.

Representative examples:

- mDNS real hardware E2E: `optional zeroconf package is not installed`
- Browser startup: `Playwright unavailable`, `launch failed`
- ONNX / YAML / ComfyUI / external inference nodes not connected

This is a **normal skip**. It's not a repair target — the environment simply lacks prerequisites.

### 4. Insufficient Test Data

Browser tests requiring images, search results, conversation logs, or multiple data items that cannot run with a lightweight database are skipped.

Representative reasons:

- `No search results available in database`
- `Skipped because no images in DB`
- `2 or more files required`
- `No prompts to test copy`

This is **generally a normal skip**. However, if a fixture should be providing the necessary data, suspect staleness.

### 5. Rate Limiting and External API Protection

Some integration tests respect external services or rate limits by skipping.

Representative reasons:

- `Skipped due to rate limit`

This is a **normal skip**.

### 6. Long-Running Fuzz / Burn-In

Burn-in under `tests/fuzz/` is for durability and crash-resilience checks, not routine regression testing.

Excluded by default via the marker pattern in `pytest.ini`.

To run:

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

Optionally:

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

This is **not mixed into normal broad runs**.

## Patterns Requiring Investigation

The following should not be dismissed as "skip is fine" but treated as test maintenance targets.

### A. Previously Passing Lightweight Tests Fall to Setup Skip

Examples:

- API smoke tests based on app/client fixtures that should be self-contained are pulled into shared server prerequisites
- Migration / schema / DB helper unit tests fall due to runtime global state initialization prerequisites

Suspect a test harness and implementation assumption mismatch.

### B. Broad Run Passes but Single Runs Fail

Typical causes:

- Depends on process-global state
- Accidentally relying on side effects initialized by an earlier test during broad run

Restore single runs to a reproducible state.

### C. Vague Skip Reasons

Bad examples:

- `failed`
- `not ready`
- `something wrong`

Skip reasons should be short statements explaining what's missing that caused the skip.

## Repair Priority

1. Fix hard failures that block broad runs
2. Fix stale tests that only break on single runs
3. Move browser / server-dependent skips toward safe skips rather than failures
4. Maintain optional skips for optional dependencies and hardware-specific tests

## What Was Fixed in This Cleanup

- Unified browser / server-dependent tests to skip safely on shared server unavailability rather than fail
- License audit now checks only `requirements*.txt` declared dependencies, not entire venv
- Test database meets path FTS prerequisites of the current search schema
- Migrations 54 / 55 are now robust to schema evolution and uninitialized runtime state

## Decision Guide When in Doubt

- Missing environment prerequisites → skip is appropriate
- Outdated expectations not matching current implementation → fix the test
- Broad run side effects in dependencies → fix implementation or test
- Unit test requiring process-global state → question the design
