/**
 * crypto-tools-app.ts — page bootstrap for /crypto-tools.
 *
 * Spec: docs/superpowers/specs/2026-05-23-crypto-tools-design.md
 */

import QRCode from "qrcode";
import jsQR from "jsqr";
import { customAlert, customConfirm } from "../shared/dialog";
import { copyToClipboard } from "../shared/clipboard";
import {
  APP_QR_MAX_BYTES,
  bytesToBase64Url,
  base64UrlToBytes,
  generateX25519KeyPair,
  generateEd25519KeyPair,
  isX25519Supported,
  isEd25519Supported,
  publicKeyFingerprint,
  exportPrivateKey,
  importPrivateKey,
  sealWithPassphrase,
  openWithPassphrase,
  sealForRecipient,
  openWithPrivateKey,
  type PublicKeyEnvelope,
  type PrivKeyExportFile,
  type PublicKeySealedPayload,
  type PassphraseSealedPayload,
  type ImportPrivateKeyResult,
} from "../crypto/subtle_ops";
import { getKey, putKey, type StoredKeyRecord } from "../crypto/key_store";

type SealedPayload = PublicKeySealedPayload | PassphraseSealedPayload;

// ─── Tab switching ──────────────────────────────────────────────────────────

function setupTabs(): void {
  const tabs = document.querySelectorAll<HTMLButtonElement>(".crypto-tab");
  const panels = document.querySelectorAll<HTMLElement>(".crypto-panel");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      tabs.forEach((t) => {
        t.classList.toggle("active", t === tab);
        t.setAttribute("aria-selected", String(t === tab));
      });
      panels.forEach((p) => p.classList.toggle("active", p.dataset.panel === target));
    });
  });
}

// ─── Toast helper ───────────────────────────────────────────────────────────

function showToast(message: string): void {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  window.setTimeout(() => el.classList.remove("show"), 2200);
}

// ─── Camera QR scanner ──────────────────────────────────────────────────────

let _cameraStream: MediaStream | null = null;
let _cameraRafId: number | null = null;
let _cameraCallback: ((text: string) => void) | null = null;
let _lastScanMs = 0;
const CAMERA_SCAN_INTERVAL_MS = 250;

function _stopCameraScanner(): void {
  if (_cameraRafId !== null) {
    cancelAnimationFrame(_cameraRafId);
    _cameraRafId = null;
  }
  if (_cameraStream) {
    _cameraStream.getTracks().forEach((t) => t.stop());
    _cameraStream = null;
  }
  const video = document.getElementById("cameraQrVideo") as HTMLVideoElement | null;
  if (video) video.srcObject = null;
  const modal = document.getElementById("cameraQrModal");
  if (modal) modal.hidden = true;
  _cameraCallback = null;
}

function _cameraQrLoop(): void {
  if (!_cameraStream || !_cameraCallback) return;
  const now = performance.now();
  if (now - _lastScanMs >= CAMERA_SCAN_INTERVAL_MS) {
    _lastScanMs = now;
    const video = document.getElementById("cameraQrVideo") as HTMLVideoElement | null;
    const canvas = document.getElementById("cameraQrCapture") as HTMLCanvasElement | null;
    if (video && canvas && video.readyState >= 2 && video.videoWidth > 0) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(video, 0, 0);
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const result = jsQR(imageData.data, canvas.width, canvas.height);
        if (result && _cameraCallback) {
          const cb = _cameraCallback;
          _stopCameraScanner();
          cb(result.data);
          return;
        }
      }
    }
  }
  _cameraRafId = requestAnimationFrame(_cameraQrLoop);
}

async function openCameraScanner(onResult: (text: string) => void): Promise<void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    await customAlert("このブラウザはカメラアクセスに対応していません。QR 画像ファイルをご利用ください。");
    return;
  }
  const modal = document.getElementById("cameraQrModal")!;
  const video = document.getElementById("cameraQrVideo") as HTMLVideoElement;
  const statusEl = document.getElementById("cameraQrStatus")!;

  _cameraCallback = onResult;
  _lastScanMs = 0;
  statusEl.textContent = "カメラを起動中...";
  modal.hidden = false;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 640 } },
    });
    // User may have pressed close while getUserMedia was pending — discard the stream.
    if (!_cameraCallback) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    _cameraStream = stream;
    video.srcObject = stream;
    await video.play();
    statusEl.textContent = "カメラを QR コードに向けてください...";
    _cameraRafId = requestAnimationFrame(_cameraQrLoop);
  } catch (e) {
    const err = e as Error;
    // AbortError from video.play() interrupted by the user pressing close
    // (_cameraCallback already null) — stop silently without showing an alert.
    if (!_cameraCallback || err.name === "AbortError") {
      _stopCameraScanner();
      return;
    }
    _stopCameraScanner();
    const msg = err.name === "NotAllowedError"
      ? "カメラのアクセスが拒否されました。ブラウザの設定でカメラを許可してください。"
      : `カメラを起動できませんでした: ${err.message}`;
    await customAlert(msg);
  }
}

// ─── QR image decoding via jsQR ─────────────────────────────────────────────

async function decodeQrFromFile(file: File): Promise<string | null> {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    await new Promise<void>((res, rej) => {
      img.onload = () => res();
      img.onerror = () => rej(new Error("image load"));
      img.src = url;
    });
    if (img.naturalWidth > 4096 || img.naturalHeight > 4096) {
      throw new Error("image too large");
    }
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const result = jsQR(data.data, canvas.width, canvas.height);
    return result ? result.data : null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

function triggerDownload(content: string, filename: string): void {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.setTimeout(() => URL.revokeObjectURL(url), 100);
}

// ─── Key management tab ─────────────────────────────────────────────────────

async function refreshKeyDisplay(): Promise<void> {
  const status = document.getElementById("keyStatus")!;
  const qrBlock = document.getElementById("keyQrBlock")!;
  const fpBlock = document.getElementById("keyFingerprintBlock")!;
  const record = await getKey();
  if (!record) {
    status.innerHTML = '<p class="key-status-empty">鍵ペアがまだ生成されていません。</p>';
    qrBlock.hidden = true;
    fpBlock.hidden = true;
    return;
  }
  status.innerHTML = `<p>✅ 鍵あり（生成: ${record.createdAt}）</p>`;
  const envelope: PublicKeyEnvelope = {
    schema: "yu://key/1",
    alg: "x25519",
    pub: record.pubRaw,
    ...(record.signPubRaw ? { sign_pub: record.signPubRaw } : {}),
  };
  const canvas = document.getElementById("keyQrCanvas") as HTMLCanvasElement;
  await QRCode.toCanvas(canvas, JSON.stringify(envelope), {
    errorCorrectionLevel: "M",
    width: 200,
  });
  qrBlock.hidden = false;
  const fp = await publicKeyFingerprint(base64UrlToBytes(record.pubRaw));
  (document.getElementById("keyFingerprint") as HTMLElement).textContent = fp;
  fpBlock.hidden = false;
}

async function handleGenerate(): Promise<void> {
  const existing = await getKey();
  if (existing) {
    const ok = await customConfirm(
      "上書きすると既存の暗号文は永久に復号できなくなります。先にエクスポートを完了させてください。本当に上書きしますか？",
      { okText: "上書きする", cancelText: "キャンセル", danger: true },
    );
    if (!ok) return;
    const reconfirm = await customConfirm(
      "もう一度確認します。本当に上書きしますか？この操作は元に戻せません。",
      { okText: "上書き確定", cancelText: "やめる", danger: true },
    );
    if (!reconfirm) return;
  }
  const { pubRaw, privJwk } = await generateX25519KeyPair();
  const record: StoredKeyRecord = {
    pubRaw: bytesToBase64Url(pubRaw),
    privJwk,
    createdAt: new Date().toISOString(),
  };
  if (await isEd25519Supported()) {
    const { signPubRaw, signPrivJwk } = await generateEd25519KeyPair();
    record.signPubRaw = bytesToBase64Url(signPubRaw);
    record.signPrivJwk = signPrivJwk;
  }
  await putKey(record);
  await refreshKeyDisplay();
  showToast("鍵ペアを生成しました。今すぐエクスポートしてください。");
  document.querySelector<HTMLDetailsElement>(".key-export-block")?.setAttribute("open", "");
  document.getElementById("exportPassphrase")?.focus();
}

async function handleCopyPub(): Promise<void> {
  const record = await getKey();
  if (!record) {
    await customAlert("鍵がありません。");
    return;
  }
  const env: PublicKeyEnvelope = {
    schema: "yu://key/1",
    alg: "x25519",
    pub: record.pubRaw,
    ...(record.signPubRaw ? { sign_pub: record.signPubRaw } : {}),
  };
  await copyToClipboard(JSON.stringify(env));
  showToast("公開鍵をコピーしました。");
}

async function handleReadPubQr(file: File): Promise<void> {
  const text = await decodeQrFromFile(file);
  if (!text) {
    await customAlert("QR コードを読み取れませんでした。");
    return;
  }
  (document.getElementById("readPubResult") as HTMLTextAreaElement).value = text;
  (document.getElementById("readPubResult") as HTMLElement).hidden = false;
  showToast("QR を読み取りました。");
}

async function handleExportKey(): Promise<void> {
  const record = await getKey();
  if (!record) {
    await customAlert("鍵がありません。");
    return;
  }
  const passEl = document.getElementById("exportPassphrase") as HTMLInputElement;
  const passphrase = passEl.value;
  try {
    const wrapped = await exportPrivateKey(record.privJwk, passphrase, record.signPrivJwk);
    triggerDownload(JSON.stringify(wrapped, null, 2), "yu-private-key.json");
    passEl.value = "";
    updateExportEnabled();
    showToast("秘密鍵をエクスポートしました。");
  } catch (e) {
    await customAlert(`エクスポートに失敗しました: ${(e as Error).message}`);
  }
}

function updateExportEnabled(): void {
  const passEl = document.getElementById("exportPassphrase") as HTMLInputElement;
  const btn = document.getElementById("exportKeyBtn") as HTMLButtonElement;
  btn.disabled = passEl.value.length < 12;
}

async function handleImportKey(): Promise<void> {
  const fileEl = document.getElementById("importKeyFile") as HTMLInputElement;
  const passEl = document.getElementById("importPassphrase") as HTMLInputElement;
  const f = fileEl.files?.[0];
  if (!f) {
    await customAlert("ファイルを選択してください。");
    return;
  }
  let parsed: PrivKeyExportFile;
  try {
    parsed = JSON.parse(await f.text()) as PrivKeyExportFile;
  } catch {
    await customAlert("ファイルの JSON 解析に失敗しました。");
    return;
  }
  if (parsed.schema !== "yu://privkey-export/1") {
    await customAlert("秘密鍵ファイルの形式が正しくありません。");
    return;
  }
  if (await getKey()) {
    const ok = await customConfirm("既存の鍵が上書きされます。続行しますか？", { danger: true });
    if (!ok) return;
  }
  try {
    const imported: ImportPrivateKeyResult = await importPrivateKey(parsed, passEl.value);
    const { privJwk, signPrivJwk } = imported;
    // RFC 8037: X25519 JWK 'x' field IS the raw 32-byte public key in
    // base64url-nopad. Validate length defensively in case a non-conforming
    // implementation ever produces a different shape.
    const pubRaw = privJwk.x;
    if (base64UrlToBytes(pubRaw).length !== 32) {
      throw new Error("imported JWK 'x' field is not a 32-byte X25519 public key");
    }
    const record: StoredKeyRecord = { pubRaw, privJwk, createdAt: new Date().toISOString() };
    if (signPrivJwk) {
      // Ed25519 JWK 'x' field is the base64url-nopad public key.
      record.signPrivJwk = signPrivJwk;
      record.signPubRaw = signPrivJwk.x;
    }
    await putKey(record);
    passEl.value = "";
    fileEl.value = "";
    await refreshKeyDisplay();
    if (signPrivJwk) {
      showToast("秘密鍵をインポートしました（署名機能あり）。");
    } else {
      showToast("秘密鍵をインポートしました。署名機能なし（古い形式のバックアップ）。");
    }
  } catch (e) {
    await customAlert(`インポートに失敗しました: ${(e as Error).message}`);
  }
}

// ─── Encryption tab ─────────────────────────────────────────────────────────

function currentEncMode(): "x25519" | "passphrase" {
  const selected = document.querySelector<HTMLInputElement>('input[name="encMode"]:checked');
  return selected?.value === "passphrase" ? "passphrase" : "x25519";
}

function setupEncModeToggle(): void {
  document.querySelectorAll<HTMLInputElement>('input[name="encMode"]').forEach((el) => {
    el.addEventListener("change", () => {
      const mode = currentEncMode();
      (document.querySelector(".enc-mode-x25519") as HTMLElement).hidden = mode !== "x25519";
      (document.querySelector(".enc-mode-passphrase") as HTMLElement).hidden = mode !== "passphrase";
    });
  });
}

async function refreshRecipientFingerprint(): Promise<void> {
  const block = document.getElementById("recipientFingerprintBlock")!;
  const fpEl = document.getElementById("recipientFingerprint")!;
  const text = (document.getElementById("recipientPub") as HTMLTextAreaElement).value.trim();
  if (!text) { block.hidden = true; return; }
  try {
    const env = JSON.parse(text) as PublicKeyEnvelope;
    if (env.schema !== "yu://key/1" || env.alg !== "x25519" || typeof env.pub !== "string") {
      block.hidden = true; return;
    }
    const pubRaw = base64UrlToBytes(env.pub);
    if (pubRaw.length !== 32) { block.hidden = true; return; }
    fpEl.textContent = await publicKeyFingerprint(pubRaw);
    block.hidden = false;
  } catch {
    block.hidden = true;
  }
}

async function handleRecipientPubQr(file: File): Promise<void> {
  const text = await decodeQrFromFile(file);
  if (!text) {
    await customAlert("QR コードを読み取れませんでした。");
    return;
  }
  (document.getElementById("recipientPub") as HTMLTextAreaElement).value = text;
  await refreshRecipientFingerprint();
}

async function handleEncrypt(): Promise<void> {
  const plain = (document.getElementById("encPlaintext") as HTMLTextAreaElement).value;
  const mode = currentEncMode();
  let payloadObj: unknown;
  try {
    if (mode === "x25519") {
      const recipText = (document.getElementById("recipientPub") as HTMLTextAreaElement).value.trim();
      const recipEnv = JSON.parse(recipText) as PublicKeyEnvelope;
      if (recipEnv.schema !== "yu://key/1" || recipEnv.alg !== "x25519") {
        await customAlert("受信者の公開鍵が yu://key/1 形式ではありません。");
        return;
      }
      const senderRecord = await getKey();
      const signPrivJwk = senderRecord?.signPrivJwk;
      const signPubRaw = senderRecord?.signPubRaw ? base64UrlToBytes(senderRecord.signPubRaw) : undefined;
      payloadObj = await sealForRecipient(plain, recipEnv, signPrivJwk, signPubRaw);
    } else {
      const pass = (document.getElementById("encPassphrase") as HTMLInputElement).value;
      if (!pass) {
        await customAlert("パスフレーズを入力してください。");
        return;
      }
      payloadObj = await sealWithPassphrase(plain, pass);
    }
  } catch (e) {
    await customAlert(`暗号化に失敗しました: ${(e as Error).message}`);
    return;
  }
  const json = JSON.stringify(payloadObj);
  const bytes = new TextEncoder().encode(json).length;
  (document.getElementById("encJson") as HTMLTextAreaElement).value = JSON.stringify(payloadObj, null, 2);
  const canvas = document.getElementById("encQrCanvas") as HTMLCanvasElement;
  const oversize = bytes > APP_QR_MAX_BYTES;
  canvas.hidden = oversize;
  (document.getElementById("encOversizeMsg") as HTMLElement).hidden = !oversize;
  if (!oversize) {
    await QRCode.toCanvas(canvas, json, { errorCorrectionLevel: "M", width: 280 });
  }
  (document.getElementById("encResultBlock") as HTMLElement).hidden = false;
}

async function handleCopyEncJson(): Promise<void> {
  const v = (document.getElementById("encJson") as HTMLTextAreaElement).value;
  await copyToClipboard(v);
  showToast("コピーしました。");
}

function handleDownloadEnc(): void {
  const v = (document.getElementById("encJson") as HTMLTextAreaElement).value;
  triggerDownload(v, "yu-seal.json");
}

// ─── Decryption tab ─────────────────────────────────────────────────────────

function parseDecInput(): SealedPayload | null {
  const raw = (document.getElementById("decInput") as HTMLTextAreaElement).value.trim();
  if (!raw) return null;
  try {
    const obj = JSON.parse(raw) as Record<string, unknown>;
    if (obj.schema !== "yu://seal/1") return null;
    return obj as unknown as SealedPayload;
  } catch {
    return null;
  }
}

function refreshDecModeHint(): void {
  const payload = parseDecInput();
  const hint = document.getElementById("decModeHint")!;
  const passRow = document.querySelector(".dec-passphrase-row") as HTMLElement;
  if (!payload) {
    hint.textContent = "";
    passRow.hidden = true;
    return;
  }
  if (payload.alg === "x25519-hkdf-sha256-aes-256-gcm") {
    hint.textContent = "公開鍵方式: IndexedDB の秘密鍵で復号します。";
    passRow.hidden = true;
  } else if (payload.alg === "pbkdf2-sha256-aes-256-gcm") {
    hint.textContent = "パスフレーズ方式: パスフレーズを入力してください。";
    passRow.hidden = false;
  } else {
    const unknownAlg = (payload as { alg?: string }).alg;
    hint.textContent = `未対応の alg: ${String(unknownAlg)}`;
    passRow.hidden = true;
  }
}

async function handleDecFileQr(file: File): Promise<void> {
  const text = await decodeQrFromFile(file);
  if (!text) {
    await customAlert("QR コードを読み取れませんでした。");
    return;
  }
  (document.getElementById("decInput") as HTMLTextAreaElement).value = text;
  refreshDecModeHint();
}

async function handleDecrypt(): Promise<void> {
  const payload = parseDecInput();
  if (!payload) {
    await customAlert("解析できませんでした。yu://seal/1 の JSON を貼り付けてください。");
    return;
  }
  try {
    let plain: string;
    let senderStatus: "verified" | "unverified" | "n/a" = "n/a";
    let senderFp: string | null = null;

    if (payload.alg === "x25519-hkdf-sha256-aes-256-gcm") {
      const record = await getKey();
      if (!record) {
        await customAlert("秘密鍵が見つかりません。鍵管理タブで生成またはインポートしてください。");
        return;
      }
      const { plaintext, sender } = await openWithPrivateKey(
        payload as PublicKeySealedPayload,
        record.privJwk,
        base64UrlToBytes(record.pubRaw),
      );
      plain = plaintext;
      senderStatus = sender.status;
      senderFp = sender.fingerprint;
    } else if (payload.alg === "pbkdf2-sha256-aes-256-gcm") {
      const pass = (document.getElementById("decPassphrase") as HTMLInputElement).value;
      plain = await openWithPassphrase(payload as PassphraseSealedPayload, pass);
    } else {
      await customAlert("このペイロードは未対応の形式です。");
      return;
    }
    (document.getElementById("decPlaintext") as HTMLTextAreaElement).value = plain;

    // If the decrypted payload is a recipe, show the bridge button.
    const recipeBtnEl = document.getElementById("decRecipeBtn");
    if (recipeBtnEl) {
      try {
        const obj = JSON.parse(plain) as Record<string, unknown>;
        recipeBtnEl.hidden = obj["schema"] !== "yu://recipe/1";
      } catch {
        recipeBtnEl.hidden = true;
      }
    }
    const senderEl = document.getElementById("decSenderStatus");
    if (senderEl) {
      if (senderStatus === "verified" && senderFp) {
        senderEl.textContent = `✅ 送信者署名確認済み（fingerprint: ${senderFp}）`;
        senderEl.className = "dec-sender-verified";
      } else if (senderStatus === "unverified") {
        senderEl.textContent = "⚠ 送信者は確認されていません（誰でもこのメッセージを作成できます）。";
        senderEl.className = "dec-sender-unverified";
      } else {
        senderEl.textContent = "";
        senderEl.className = "";
      }
    }
    (document.getElementById("decResultBlock") as HTMLElement).hidden = false;
  } catch (e) {
    await customAlert("復号できませんでした。正しい鍵またはパスフレーズか確認してください。");
    console.error(e);
  }
}

async function handleCopyDec(): Promise<void> {
  const v = (document.getElementById("decPlaintext") as HTMLTextAreaElement).value;
  await copyToClipboard(v);
  showToast("コピーしました。");
}

// ─── Bootstrap ──────────────────────────────────────────────────────────────

async function boot(): Promise<void> {
  setupTabs();
  const x25519 = await isX25519Supported();
  if (!x25519) {
    document.getElementById("cryptoUnsupportedBanner")!.hidden = false;
    document.getElementById("generateKeyBtn")?.setAttribute("disabled", "");
  }

  // Camera modal close
  document.getElementById("cameraQrClose")?.addEventListener("click", _stopCameraScanner);

  // Key management
  document.getElementById("generateKeyBtn")?.addEventListener("click", () => { void handleGenerate(); });
  document.getElementById("copyPubKeyBtn")?.addEventListener("click", () => { void handleCopyPub(); });
  document.getElementById("readPubQrFile")?.addEventListener("change", (e) => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) void handleReadPubQr(f);
  });
  document.getElementById("readPubQrCamera")?.addEventListener("click", () => {
    void openCameraScanner((text) => {
      (document.getElementById("readPubResult") as HTMLTextAreaElement).value = text;
      (document.getElementById("readPubResult") as HTMLElement).hidden = false;
      showToast("QR を読み取りました。");
    });
  });
  document.getElementById("exportPassphrase")?.addEventListener("input", updateExportEnabled);
  document.getElementById("exportKeyBtn")?.addEventListener("click", () => { void handleExportKey(); });
  document.getElementById("importKeyBtn")?.addEventListener("click", () => { void handleImportKey(); });

  // Encryption
  setupEncModeToggle();
  document.getElementById("recipientPub")?.addEventListener("input", () => { void refreshRecipientFingerprint(); });
  document.getElementById("recipientPubFile")?.addEventListener("change", (e) => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) void handleRecipientPubQr(f);
  });
  document.getElementById("recipientPubCamera")?.addEventListener("click", () => {
    void openCameraScanner((text) => {
      (document.getElementById("recipientPub") as HTMLTextAreaElement).value = text;
      void refreshRecipientFingerprint();
    });
  });
  document.getElementById("encryptBtn")?.addEventListener("click", () => { void handleEncrypt(); });
  document.getElementById("copyEncJsonBtn")?.addEventListener("click", () => { void handleCopyEncJson(); });
  document.getElementById("downloadEncBtn")?.addEventListener("click", handleDownloadEnc);

  if (!x25519) {
    const x25Radio = document.querySelector<HTMLInputElement>('input[name="encMode"][value="x25519"]');
    if (x25Radio) {
      x25Radio.disabled = true;
      x25Radio.checked = false;
    }
    const passRadio = document.querySelector<HTMLInputElement>('input[name="encMode"][value="passphrase"]');
    if (passRadio) passRadio.checked = true;
    (document.querySelector(".enc-mode-x25519") as HTMLElement).hidden = true;
    (document.querySelector(".enc-mode-passphrase") as HTMLElement).hidden = false;
  }

  // Decryption
  document.getElementById("decInput")?.addEventListener("input", refreshDecModeHint);
  document.getElementById("decFileQr")?.addEventListener("change", (e) => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) void handleDecFileQr(f);
  });
  document.getElementById("decCameraQr")?.addEventListener("click", () => {
    void openCameraScanner((text) => {
      (document.getElementById("decInput") as HTMLTextAreaElement).value = text;
      refreshDecModeHint();
    });
  });
  document.getElementById("decryptBtn")?.addEventListener("click", () => { void handleDecrypt(); });
  document.getElementById("copyDecBtn")?.addEventListener("click", () => { void handleCopyDec(); });
  document.getElementById("decRecipeBtn")?.addEventListener("click", () => {
    const plain = (document.getElementById("decPlaintext") as HTMLTextAreaElement).value;
    void import("../recipe_share").then(({ openImportModal }) => {
      try {
        const recipe = JSON.parse(plain) as Parameters<typeof openImportModal>[0];
        void openImportModal(recipe);
      } catch {
        void customAlert("レシピの解析に失敗しました。");
      }
    });
  });

  await refreshKeyDisplay();
}

document.addEventListener("DOMContentLoaded", () => { void boot(); });

export {};
