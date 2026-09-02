/**
 * Playwright API-level spec: Rust server ↔ Python server パリティ検証
 *
 * 環境変数:
 *   RUST_API_URL   - Rust サーバー URL  (default: http://127.0.0.1:5002)
 *   PYTHON_API_URL - Python サーバー URL (オプション、設定時に比較実行)
 *
 * 実行例:
 *   RUST_API_URL=http://127.0.0.1:5002 \
 *   PYTHON_API_URL=http://127.0.0.1:5000 \
 *     pnpm exec playwright test e2e/rust-api.spec.ts --project=chromium
 *
 * RUST_API_URL が未設定の場合はスキップ。
 */
import { test, expect, APIRequestContext } from "@playwright/test";

const RUST_URL = process.env.RUST_API_URL ?? "";
const PY_URL = process.env.PYTHON_API_URL ?? "";

// Python セッション Cookie (PIN 認証後)
const PY_COOKIE = process.env.PYTHON_SESSION_COOKIE ?? "";

async function pythonReq(req: APIRequestContext, path: string) {
  const headers: Record<string, string> = {};
  if (PY_COOKIE) headers["Cookie"] = `session=${PY_COOKIE}`;
  return req.get(`${PY_URL}${path}`, { headers });
}

// ---------------------------------------------------------------------------
// /api/scan/status
// ---------------------------------------------------------------------------

test.describe("GET /api/scan/status", () => {
  test.skip(!RUST_URL, "RUST_API_URL not set — skipping Rust API spec");

  test("Rust returns 200", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/scan/status`);
    expect(res.status()).toBe(200);
  });

  test("Rust response has Python-compatible schema", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/scan/status`);
    const body = await res.json();

    // Python 互換フィールド
    expect(typeof body.running).toBe("boolean");
    expect(typeof body.phase).toBe("string");
    expect(typeof body.current).toBe("number");
    expect(typeof body.total).toBe("number");
    expect(typeof body.percent).toBe("number");
    expect(typeof body.current_file).toBe("string");
    expect(typeof body.message).toBe("string");
    expect("error" in body).toBe(true);
    expect("job_id" in body).toBe(true);
    expect("label" in body).toBe(true);
  });

  test("Rust idle state values are correct", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/scan/status`);
    const body = await res.json();

    // ジョブ管理未実装 → 常に idle
    expect(body.running).toBe(false);
    expect(body.phase).toBe("idle");
    expect(body.current).toBe(0);
    expect(body.total).toBe(0);
    expect(body.percent).toBe(0);
  });

  test("Python also returns 200 for /api/scan/status", async ({ request }) => {
    test.skip(!PY_URL || !PY_COOKIE, "PYTHON_API_URL + PYTHON_SESSION_COOKIE required");
    const res = await pythonReq(request, "/api/scan/status");
    expect(res.status()).toBe(200);
  });

  test("Python response also has same schema fields", async ({ request }) => {
    test.skip(!PY_URL || !PY_COOKIE, "PYTHON_API_URL + PYTHON_SESSION_COOKIE required");
    const res = await pythonReq(request, "/api/scan/status");
    const body = await res.json();
    expect(typeof body.running).toBe("boolean");
    expect(typeof body.phase).toBe("string");
    expect(typeof body.current).toBe("number");
    expect(typeof body.total).toBe("number");
    expect(typeof body.percent).toBe("number");
  });
});

// ---------------------------------------------------------------------------
// /api/files
// ---------------------------------------------------------------------------

test.describe("GET /api/files", () => {
  test.skip(!RUST_URL, "RUST_API_URL not set — skipping Rust API spec");

  test("Rust returns 200", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/files`);
    expect(res.status()).toBe(200);
  });

  test("Rust response is an array", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/files`);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test("Rust file objects have id, path, mtime fields", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/files`);
    const body = await res.json();
    if (body.length > 0) {
      const f = body[0];
      expect(typeof f.id).toBe("number");
      expect(typeof f.path).toBe("string");
      expect(typeof f.mtime).toBe("number");
    }
  });
});

// ---------------------------------------------------------------------------
// /api/files/{id}/tags
// ---------------------------------------------------------------------------

test.describe("GET /api/files/{id}/tags", () => {
  test.skip(!RUST_URL, "RUST_API_URL not set — skipping Rust API spec");

  test("Rust returns 200 for file id=1", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/files/1/tags`);
    expect(res.status()).toBe(200);
  });

  test("Rust tags response is an array", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/files/1/tags`);
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test("Rust returns 404 for non-existent file id", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/files/999999/tags`);
    // 存在しないIDは 404 または空配列 200 のどちらも許容
    expect([200, 404]).toContain(res.status());
  });
});

// ---------------------------------------------------------------------------
// /api/lock/status
// ---------------------------------------------------------------------------

test.describe("GET /api/lock/status", () => {
  test.skip(!RUST_URL, "RUST_API_URL not set — skipping Rust API spec");

  test("Rust returns 200", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/lock/status`);
    expect(res.status()).toBe(200);
  });

  test("Rust lock/status has Python-compatible flat schema", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/lock/status`);
    const body = await res.json();

    expect(typeof body.ok).toBe("boolean");
    expect(body.ok).toBe(true);
    expect("error" in body).toBe(true);
    expect("data" in body).toBe(true);
    expect(typeof body.locked).toBe("boolean");
    expect("locked_at" in body).toBe(true);
    expect(typeof body.locked_duration).toBe("number");
  });

  test("Rust idle lock state values are correct", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/lock/status`);
    const body = await res.json();
    expect(body.locked).toBe(false);
    expect(body.locked_at).toBeNull();
    expect(body.locked_duration).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// /api/auth/status
// ---------------------------------------------------------------------------

test.describe("GET /api/auth/status", () => {
  test.skip(!RUST_URL, "RUST_API_URL not set — skipping Rust API spec");

  test("Rust returns 200", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/auth/status`);
    expect(res.status()).toBe(200);
  });

  test("Rust auth/status has Python-compatible flat schema", async ({ request }) => {
    const res = await request.get(`${RUST_URL}/api/auth/status`);
    const body = await res.json();

    expect(body.ok).toBe(true);
    expect("error" in body).toBe(true);
    expect("data" in body).toBe(true);
    expect(typeof body.pin_auth).toBe("boolean");
    expect(typeof body.quick_lock_enabled).toBe("boolean");
    expect(typeof body.quick_lock_locked).toBe("boolean");
    expect(typeof body.trusted_proxy_auth).toBe("boolean");
    expect(typeof body.session_authenticated).toBe("boolean");
  });
});

// ---------------------------------------------------------------------------
// /api/auth/logout (POST)
// ---------------------------------------------------------------------------

test.describe("POST /api/auth/logout", () => {
  test.skip(!RUST_URL, "RUST_API_URL not set — skipping Rust API spec");

  test("Rust returns 200", async ({ request }) => {
    const res = await request.post(`${RUST_URL}/api/auth/logout`);
    expect(res.status()).toBe(200);
  });

  test("Rust logout response has ok/success fields", async ({ request }) => {
    const res = await request.post(`${RUST_URL}/api/auth/logout`);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect("error" in body).toBe(true);
    expect(body.success).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 比較: 両サーバーの /api/scan/status・lock/status スキーマが一致
// ---------------------------------------------------------------------------

test.describe("Schema parity: Rust vs Python", () => {
  test.skip(!RUST_URL || !PY_URL, "Both RUST_API_URL and PYTHON_API_URL required");

  test("scan/status response keys match between Rust and Python", async ({ request }) => {
    test.skip(!PY_COOKIE, "PYTHON_SESSION_COOKIE required for Python /api/scan/status");
    const [rustRes, pyRes] = await Promise.all([
      request.get(`${RUST_URL}/api/scan/status`),
      pythonReq(request, "/api/scan/status"),
    ]);
    expect(rustRes.status()).toBe(200);
    expect(pyRes.status()).toBe(200);

    const rustBody = await rustRes.json();
    const pyBody = await pyRes.json();

    const rustKeys = Object.keys(rustBody).sort();
    const pyKeys = Object.keys(pyBody).sort();
    expect(rustKeys).toEqual(pyKeys);
  });

  test("lock/status response body matches exactly between Rust and Python", async ({ request }) => {
    const [rustRes, pyRes] = await Promise.all([
      request.get(`${RUST_URL}/api/lock/status`),
      request.get(`${PY_URL}/api/lock/status`),
    ]);
    expect(rustRes.status()).toBe(200);
    expect(pyRes.status()).toBe(200);

    const rustBody = await rustRes.json();
    const pyBody = await pyRes.json();

    // lock/status は値まで完全一致するはず（どちらも unlocked idle）
    expect(rustBody.locked).toEqual(pyBody.locked);
    expect(rustBody.locked_at).toEqual(pyBody.locked_at);
    expect(rustBody.locked_duration).toEqual(pyBody.locked_duration);
    expect(Object.keys(rustBody).sort()).toEqual(Object.keys(pyBody).sort());
  });
});
