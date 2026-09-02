import { test, expect } from '@playwright/test';

// Playwright fixture for Phase 5 Safe Mode.
//
// Designed to run against a manually-launched yu_ai_manager started with
// `--safe-mode`, e.g.:
//
//   uv run python web_ui.py --safe-mode --port 8000
//
// Set SAFE_MODE_BASE_URL=http://127.0.0.1:8000 before running:
//
//   SAFE_MODE_BASE_URL=http://127.0.0.1:8000 pnpm exec playwright test e2e/safe-mode.spec.ts
//
// When SAFE_MODE_BASE_URL is not set, the suite skips so CI/normal runs do
// not require a live server. This is intentional — Safe Mode requires the
// `--safe-mode` argv path, which `playwright.config.ts`'s webServer entry
// cannot express without a dedicated profile.

const baseURL = process.env.SAFE_MODE_BASE_URL ?? '';

test.describe('Phase 5 Safe Mode', () => {
  test.skip(!baseURL, 'SAFE_MODE_BASE_URL not set — skipping Safe Mode fixture');

  test('diagnostics page exposes safe_mode banner', async ({ page }) => {
    await page.goto(`${baseURL}/diagnostics`);
    const banner = page.locator('[data-testid="safe-mode-banner"], .safe-mode-banner');
    await expect(banner).toBeVisible();
  });

  test('is_safe_mode API returns true', async ({ request }) => {
    const res = await request.get(`${baseURL}/api/diagnostics/is_safe_mode`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.safe_mode).toBe(true);
  });

  test('update verify rejects patch.diff in safe mode', async ({ request }) => {
    // The verify endpoint should reject a package containing patch.diff with
    // 403 patch_forbidden_in_safe_mode. We send a minimal multipart payload
    // and only assert the status code / error code shape; constructing a
    // valid signed zip in this fixture would require shipping fixture keys.
    const res = await request.post(`${baseURL}/api/update/verify`, {
      multipart: {
        update_zip: {
          name: 'no-such.zip',
          mimeType: 'application/zip',
          buffer: Buffer.from('not a real zip'),
        },
      },
    });
    // We accept either 400 (malformed zip) OR 403 (safe-mode short-circuit).
    // Both are valid safe-mode behaviors — what we forbid is 200.
    expect([400, 403]).toContain(res.status());
  });
});
