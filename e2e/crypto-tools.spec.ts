/**
 * Playwright E2E for /crypto-tools.
 *
 * Run against a manually-launched yu_ai_manager logged in as admin:
 *
 *   CRYPTO_TOOLS_BASE_URL=http://127.0.0.1:8000 \
 *     pnpm exec playwright test e2e/crypto-tools.spec.ts
 *
 * Skipped when CRYPTO_TOOLS_BASE_URL is unset so CI / normal runs do not
 * require a live server. The server must be authenticated in the browser
 * context that Playwright uses (storage state) or run with no auth.
 */
import { expect, test } from "@playwright/test";

const baseURL = process.env.CRYPTO_TOOLS_BASE_URL ?? "";

test.describe("crypto-tools", () => {
  test.skip(!baseURL, "CRYPTO_TOOLS_BASE_URL not set — skipping E2E");

  test.beforeEach(async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto(`${baseURL}/crypto-tools`);
    // Wipe IDB so each test starts from a clean state.
    await page.evaluate(() => indexedDB.deleteDatabase("yu-crypto-v1"));
    await page.reload();
  });

  test("passphrase round-trip", async ({ page }) => {
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "correct horse battery staple");
    await page.fill("#encPlaintext", "hello, world");
    await page.click("#encryptBtn");
    const json = await page.locator("#encJson").inputValue();
    expect(json).toContain('"pbkdf2-sha256-aes-256-gcm"');

    await page.click('text=🔓 復号');
    await page.fill("#decInput", json);
    await page.fill("#decPassphrase", "correct horse battery staple");
    await page.click("#decryptBtn");
    await expect(page.locator("#decPlaintext")).toHaveValue("hello, world");
  });

  test("passphrase wrong → fail", async ({ page }) => {
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "right-passphrase");
    await page.fill("#encPlaintext", "secret");
    await page.click("#encryptBtn");
    const json = await page.locator("#encJson").inputValue();
    await page.click('text=🔓 復号');
    await page.fill("#decInput", json);
    await page.fill("#decPassphrase", "wrong-passphrase");
    page.on("dialog", (d) => d.accept());
    await page.click("#decryptBtn");
    // Result block should remain hidden — decryption failed.
    await expect(page.locator("#decResultBlock")).toBeHidden();
  });

  test("public-key round-trip", async ({ page }) => {
    await page.click("#generateKeyBtn");
    await page.waitForSelector("#keyFingerprint:not(:empty)");
    await page.click("#copyPubKeyBtn");
    const pubJson = await page.evaluate(() => navigator.clipboard.readText());

    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="x25519"]');
    await page.fill("#recipientPub", pubJson);
    await page.fill("#encPlaintext", "x25519 test");
    await page.click("#encryptBtn");
    const json = await page.locator("#encJson").inputValue();

    await page.click('text=🔓 復号');
    await page.fill("#decInput", json);
    await page.click("#decryptBtn");
    await expect(page.locator("#decPlaintext")).toHaveValue("x25519 test");
  });

  test("ciphertext tamper (1 byte flip) → fail", async ({ page }) => {
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "passphrase-12char+");
    await page.fill("#encPlaintext", "to be tampered");
    await page.click("#encryptBtn");
    const original = JSON.parse(await page.locator("#encJson").inputValue());
    const ct = original.ciphertext as string;
    const flipChar = ct[0] === "A" ? "B" : "A";
    original.ciphertext = flipChar + ct.slice(1);
    await page.click('text=🔓 復号');
    await page.fill("#decInput", JSON.stringify(original));
    await page.fill("#decPassphrase", "passphrase-12char+");
    page.on("dialog", (d) => d.accept());
    await page.click("#decryptBtn");
    await expect(page.locator("#decResultBlock")).toBeHidden();
  });

  test("GCM tag truncated → fail", async ({ page }) => {
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "passphrase-12char+");
    await page.fill("#encPlaintext", "tag truncate test");
    await page.click("#encryptBtn");
    const obj = JSON.parse(await page.locator("#encJson").inputValue());
    obj.ciphertext = (obj.ciphertext as string).slice(0, -2);
    await page.click('text=🔓 復号');
    await page.fill("#decInput", JSON.stringify(obj));
    await page.fill("#decPassphrase", "passphrase-12char+");
    page.on("dialog", (d) => d.accept());
    await page.click("#decryptBtn");
    await expect(page.locator("#decResultBlock")).toBeHidden();
  });

  test("ephemeral_pub tamper → fail (HKDF context binding test)", async ({ page }) => {
    await page.click("#generateKeyBtn");
    await page.waitForSelector("#keyFingerprint:not(:empty)");
    await page.click("#copyPubKeyBtn");
    const pubJson = await page.evaluate(() => navigator.clipboard.readText());
    await page.click('text=🔒 暗号化');
    await page.fill("#recipientPub", pubJson);
    await page.fill("#encPlaintext", "binding test");
    await page.click("#encryptBtn");
    const obj = JSON.parse(await page.locator("#encJson").inputValue());
    const ep = obj.ephemeral_pub as string;
    obj.ephemeral_pub = (ep[0] === "A" ? "B" : "A") + ep.slice(1);
    await page.click('text=🔓 復号');
    await page.fill("#decInput", JSON.stringify(obj));
    page.on("dialog", (d) => d.accept());
    await page.click("#decryptBtn");
    await expect(page.locator("#decResultBlock")).toBeHidden();
  });

  test("schema mismatch (yu://recipe/1) → error", async ({ page }) => {
    await page.click('text=🔓 復号');
    await page.fill("#decInput", JSON.stringify({ schema: "yu://recipe/1", bridge_id: "nai" }));
    page.on("dialog", (d) => d.accept());
    await page.click("#decryptBtn");
    await expect(page.locator("#decResultBlock")).toBeHidden();
  });

  test("unicode round-trip", async ({ page }) => {
    const text = "日本語🔐مرحبا\nThird line";
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "unicode-test-12+");
    await page.fill("#encPlaintext", text);
    await page.click("#encryptBtn");
    const json = await page.locator("#encJson").inputValue();
    await page.click('text=🔓 復号');
    await page.fill("#decInput", json);
    await page.fill("#decPassphrase", "unicode-test-12+");
    await page.click("#decryptBtn");
    await expect(page.locator("#decPlaintext")).toHaveValue(text);
  });

  test("empty plaintext round-trip", async ({ page }) => {
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "empty-test-12char");
    await page.fill("#encPlaintext", "");
    await page.click("#encryptBtn");
    const json = await page.locator("#encJson").inputValue();
    await page.click('text=🔓 復号');
    await page.fill("#decInput", json);
    await page.fill("#decPassphrase", "empty-test-12char");
    await page.click("#decryptBtn");
    await expect(page.locator("#decPlaintext")).toHaveValue("");
  });

  test("oversize plaintext → QR disabled, download available", async ({ page }) => {
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "oversize-test-12+");
    await page.fill("#encPlaintext", "x".repeat(3000));
    await page.click("#encryptBtn");
    await expect(page.locator("#encQrCanvas")).toBeHidden();
    await expect(page.locator("#encOversizeMsg")).toBeVisible();
    await expect(page.locator("#downloadEncBtn")).toBeVisible();
  });

  test("export button disabled when passphrase < 12 chars", async ({ page }) => {
    await page.click("#generateKeyBtn");
    await page.waitForSelector("#keyFingerprint:not(:empty)");
    await page.locator(".key-export-block").evaluate((el: HTMLElement) => el.setAttribute("open", ""));
    await page.fill("#exportPassphrase", "short");
    await expect(page.locator("#exportKeyBtn")).toBeDisabled();
    await page.fill("#exportPassphrase", "long-enough-12+");
    await expect(page.locator("#exportKeyBtn")).toBeEnabled();
  });

  test("export → wipe → import → decrypt", async ({ page }) => {
    // Generate key
    await page.click("#generateKeyBtn");
    await page.waitForSelector("#keyFingerprint:not(:empty)");
    await page.click("#copyPubKeyBtn");
    const pubJson = await page.evaluate(() => navigator.clipboard.readText());

    // Encrypt a message to it
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="x25519"]');
    await page.fill("#recipientPub", pubJson);
    await page.fill("#encPlaintext", "durable");
    await page.click("#encryptBtn");
    const sealedJson = await page.locator("#encJson").inputValue();

    // Export private key
    await page.click('text=🔑 鍵管理');
    await page.locator(".key-export-block").evaluate((el: HTMLElement) => el.setAttribute("open", ""));
    await page.fill("#exportPassphrase", "export-passphrase-12+");
    const downloadPromise = page.waitForEvent("download");
    await page.click("#exportKeyBtn");
    const download = await downloadPromise;
    const stream = (await download.createReadStream())!;
    const chunks: Buffer[] = [];
    for await (const c of stream) chunks.push(Buffer.from(c));
    const exportedJson = Buffer.concat(chunks).toString("utf-8");

    // Wipe IDB
    await page.evaluate(() => indexedDB.deleteDatabase("yu-crypto-v1"));
    await page.reload();
    await expect(page.locator(".key-status-empty")).toBeVisible();

    // Import
    await page.locator(".key-import-block").evaluate((el: HTMLElement) => el.setAttribute("open", ""));
    await page.setInputFiles("#importKeyFile", {
      name: "yu-private-key.json",
      mimeType: "application/json",
      buffer: Buffer.from(exportedJson, "utf-8"),
    });
    await page.fill("#importPassphrase", "export-passphrase-12+");
    await page.click("#importKeyBtn");
    await page.waitForSelector("#keyFingerprint:not(:empty)");

    // Decrypt should now succeed using the restored key
    await page.click('text=🔓 復号');
    await page.fill("#decInput", sealedJson);
    await page.click("#decryptBtn");
    await expect(page.locator("#decPlaintext")).toHaveValue("durable");
  });

  test("sealed payload carries aad:1 field", async ({ page }) => {
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "aad-field-test-12");
    await page.fill("#encPlaintext", "aad check");
    await page.click("#encryptBtn");
    const obj = JSON.parse(await page.locator("#encJson").inputValue());
    expect(obj.aad).toBe(1);
  });

  test("iv tamper on aad-protected payload → fail", async ({ page }) => {
    await page.click('text=🔒 暗号化');
    await page.click('input[name="encMode"][value="passphrase"]');
    await page.fill("#encPassphrase", "iv-tamper-test-12");
    await page.fill("#encPlaintext", "integrity check");
    await page.click("#encryptBtn");
    const obj = JSON.parse(await page.locator("#encJson").inputValue());
    // Flip the first character of IV to produce a different nonce
    const iv = obj.iv as string;
    obj.iv = (iv[0] === "A" ? "B" : "A") + iv.slice(1);
    await page.click('text=🔓 復号');
    await page.fill("#decInput", JSON.stringify(obj));
    await page.fill("#decPassphrase", "iv-tamper-test-12");
    page.on("dialog", (d) => d.accept());
    await page.click("#decryptBtn");
    await expect(page.locator("#decResultBlock")).toBeHidden();
  });
});
