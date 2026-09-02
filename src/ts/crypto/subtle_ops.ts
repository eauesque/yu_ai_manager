/**
 * subtle_ops.ts — pure-function wrappers over Web Crypto API.
 *
 * No side effects: no IndexedDB, no DOM. Tested via Playwright by exercising
 * the UI; can be unit-tested with Vitest in the future.
 *
 * See docs/superpowers/specs/2026-05-23-crypto-tools-design.md
 */

export const APP_QR_MAX_BYTES = 2150;
export const PBKDF2_ITERATIONS = 600_000;  // OWASP 2023. Re-evaluate 2027 Q1.
// Maximum accepted iteration count when decrypting. Caps adversary-controlled
// values from sealed payloads to prevent main-thread DoS via huge counts.
export const PBKDF2_MAX_ITERATIONS = 10_000_000;
export const HKDF_INFO_BASE = "yu://seal/1";
const ED25519_ALG = { name: "Ed25519" } as unknown as AlgorithmIdentifier;

// ─── base64url (RFC 4648 §5, no padding) ────────────────────────────────────

export function bytesToBase64Url(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function base64UrlToBytes(s: string): Uint8Array {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// ─── JWK normalization ──────────────────────────────────────────────────────

export interface NormalizedEd25519Jwk {
  kty: "OKP";
  crv: "Ed25519";
  x: string;
  d?: string;
}

export interface NormalizedX25519Jwk {
  kty: "OKP";
  crv: "X25519";
  x: string;
  d?: string;
}

export function normalizeJwk(jwk: JsonWebKey): NormalizedX25519Jwk {
  const out: Record<string, unknown> = { ...jwk };
  delete out.alg;  // Browser-dependent value; importKey ignores it
  // Some implementations may use "X-25519" (hyphenated); accept both.
  if (out.crv === "X-25519") out.crv = "X25519";
  if (out.kty !== "OKP") throw new Error(`Unexpected JWK kty: ${String(out.kty)}`);
  if (out.crv !== "X25519") throw new Error(`Unexpected JWK crv: ${String(out.crv)}`);
  if (typeof out.x !== "string") throw new Error("JWK missing x");
  return out as unknown as NormalizedX25519Jwk;
}

// ─── Feature detection ──────────────────────────────────────────────────────

export async function isEd25519Supported(): Promise<boolean> {
  try {
    await crypto.subtle.generateKey(ED25519_ALG, false, ["sign", "verify"]);
    return true;
  } catch {
    return false;
  }
}

export async function isX25519Supported(): Promise<boolean> {
  try {
    const kp = await crypto.subtle.generateKey(
      { name: "X25519" } as unknown as AlgorithmIdentifier,
      true,
      ["deriveBits"],
    ) as CryptoKeyPair;
    const raw = await crypto.subtle.exportKey("raw", kp.publicKey);
    await crypto.subtle.importKey(
      "raw",
      raw,
      { name: "X25519" } as unknown as AlgorithmIdentifier,
      false,
      [],
    );
    return true;
  } catch {
    return false;
  }
}

// ─── Random helpers ─────────────────────────────────────────────────────────

export function randomBytes(n: number): Uint8Array {
  const buf = new Uint8Array(n);
  crypto.getRandomValues(buf);
  return buf;
}

// ─── Fingerprint (SHA-256 first 16 bytes, hex grouped by 4) ─────────────────

export async function publicKeyFingerprint(pubRaw: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", pubRaw as unknown as BufferSource);
  const head = new Uint8Array(digest).slice(0, 16);
  const hex = Array.from(head).map((b) => b.toString(16).padStart(2, "0")).join("");
  // Group by 4 hex chars for readability: "a3f2 8b4c 1e09 77d2 4f5e 6a7b 8c9d e0f1"
  return hex.match(/.{1,4}/g)!.join(" ");
}

// ─── Ed25519 signing key pair ────────────────────────────────────────────────

export interface Ed25519KeyPairExport {
  signPubRaw: Uint8Array;
  signPrivJwk: NormalizedEd25519Jwk;
}

export async function generateEd25519KeyPair(): Promise<Ed25519KeyPairExport> {
  const kp = (await crypto.subtle.generateKey(ED25519_ALG, true, ["sign", "verify"])) as CryptoKeyPair;
  const signPubRaw = new Uint8Array(await crypto.subtle.exportKey("raw", kp.publicKey));
  const signPrivJwk = (await crypto.subtle.exportKey("jwk", kp.privateKey)) as unknown as NormalizedEd25519Jwk;
  return { signPubRaw, signPrivJwk };
}

export async function signWithEd25519(
  privJwk: NormalizedEd25519Jwk,
  data: Uint8Array,
): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey("jwk", privJwk as unknown as JsonWebKey, ED25519_ALG, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign(ED25519_ALG, key, data as unknown as BufferSource));
}

export async function verifyWithEd25519(
  pubRaw: Uint8Array,
  sig: Uint8Array,
  data: Uint8Array,
): Promise<boolean> {
  try {
    const key = await crypto.subtle.importKey("raw", pubRaw as unknown as BufferSource, ED25519_ALG, false, ["verify"]);
    return await crypto.subtle.verify(ED25519_ALG, key, sig as unknown as BufferSource, data as unknown as BufferSource);
  } catch {
    return false;
  }
}

// ─── Sender verification result ──────────────────────────────────────────────

export interface SenderVerification {
  status: "verified" | "unverified";
  fingerprint: string | null;
}

// ─── Passphrase mode: PBKDF2 + AES-256-GCM ─────────────────────────────────

export interface PassphraseSealedPayload {
  schema: "yu://seal/1";
  alg: "pbkdf2-sha256-aes-256-gcm";
  pbkdf2_salt: string;
  pbkdf2_iterations: number;
  iv: string;
  ciphertext: string;
  aad?: 1;  // present when AAD was applied; absent in payloads created before v4.225.8
}

async function deriveAesKeyFromPassphrase(
  passphrase: string,
  salt: Uint8Array,
  iterations: number,
  usage: KeyUsage,
): Promise<CryptoKey> {
  const passKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase) as unknown as BufferSource,
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt: salt as unknown as BufferSource, iterations },
    passKey,
    { name: "AES-GCM", length: 256 },  // length:256 REQUIRED — never omit
    false,
    [usage],
  );
}

function buildPassphraseAad(
  schema: string,
  alg: string,
  pbkdf2Salt: Uint8Array,
  pbkdf2Iterations: number,
  iv: Uint8Array,
): Uint8Array {
  return buildAad([schema, alg, pbkdf2Salt, uint32BeBytes(pbkdf2Iterations), iv]);
}

export async function sealWithPassphrase(
  plaintext: string,
  passphrase: string,
): Promise<PassphraseSealedPayload> {
  const salt = randomBytes(16);
  const iv = randomBytes(12);
  const aesKey = await deriveAesKeyFromPassphrase(passphrase, salt, PBKDF2_ITERATIONS, "encrypt");
  const aadBytes = buildPassphraseAad("yu://seal/1", "pbkdf2-sha256-aes-256-gcm", salt, PBKDF2_ITERATIONS, iv);
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: iv as unknown as BufferSource, additionalData: aadBytes as unknown as BufferSource },
      aesKey,
      new TextEncoder().encode(plaintext) as unknown as BufferSource,
    ),
  );
  return {
    schema: "yu://seal/1",
    alg: "pbkdf2-sha256-aes-256-gcm",
    pbkdf2_salt: bytesToBase64Url(salt),
    pbkdf2_iterations: PBKDF2_ITERATIONS,
    iv: bytesToBase64Url(iv),
    ciphertext: bytesToBase64Url(ciphertext),
    aad: 1,
  };
}

export async function openWithPassphrase(
  payload: PassphraseSealedPayload,
  passphrase: string,
): Promise<string> {
  if (payload.schema !== "yu://seal/1") throw new Error("unsupported schema");
  if (payload.alg !== "pbkdf2-sha256-aes-256-gcm") throw new Error("unsupported alg");
  const salt = base64UrlToBytes(payload.pbkdf2_salt);
  const iv = base64UrlToBytes(payload.iv);
  const ciphertext = base64UrlToBytes(payload.ciphertext);
  const iterations = payload.pbkdf2_iterations || PBKDF2_ITERATIONS;
  if (iterations > PBKDF2_MAX_ITERATIONS) {
    throw new Error(`pbkdf2_iterations exceeds maximum (${PBKDF2_MAX_ITERATIONS})`);
  }
  const aesKey = await deriveAesKeyFromPassphrase(passphrase, salt, iterations, "decrypt");
  const gcmParams: AesGcmParams = { name: "AES-GCM", iv: iv as unknown as BufferSource };
  if (payload.aad === 1) {
    gcmParams.additionalData = buildPassphraseAad(
      payload.schema, payload.alg, salt, iterations, iv,
    ) as unknown as BufferSource;
  }
  const plain = await crypto.subtle.decrypt(gcmParams, aesKey, ciphertext as unknown as BufferSource);
  return new TextDecoder().decode(plain);
}

// ─── Public key mode: X25519 + HKDF-SHA256 + AES-256-GCM ───────────────────

const X25519_ALG = { name: "X25519" } as unknown as AlgorithmIdentifier;

export interface PublicKeyEnvelope {
  schema: "yu://key/1";
  alg: "x25519";
  pub: string;       // base64url of 32-byte raw X25519 public key
  sign_pub?: string; // base64url of 32-byte raw Ed25519 public key (optional)
}

export interface PublicKeySealedPayload {
  schema: "yu://seal/1";
  alg: "x25519-hkdf-sha256-aes-256-gcm";
  ephemeral_pub: string;
  hkdf_salt: string;
  iv: string;
  ciphertext: string;
  aad?: 1;             // present when AAD was applied; absent in payloads created before v4.225.8
  sender_sign_pub?: string;  // base64url Ed25519 public key of sender (optional)
  sender_sig?: string;       // base64url Ed25519 signature over ciphertext bytes (optional)
}

export interface X25519KeyPairExport {
  pubRaw: Uint8Array;
  privJwk: NormalizedX25519Jwk;
}

export async function generateX25519KeyPair(): Promise<X25519KeyPairExport> {
  const kp = (await crypto.subtle.generateKey(
    X25519_ALG,
    true,  // extractable: only needed to export JWK once; working keys use false
    ["deriveKey", "deriveBits"],
  )) as CryptoKeyPair;
  const pubRaw = new Uint8Array(await crypto.subtle.exportKey("raw", kp.publicKey));
  const privJwk = normalizeJwk(await crypto.subtle.exportKey("jwk", kp.privateKey));
  return { pubRaw, privJwk };
}

async function importEphemeralPub(raw: Uint8Array): Promise<CryptoKey> {
  // CRITICAL: public-key import REQUIRES keyUsages: [] (deriveBits belongs to
  // the private key side only). Passing ["deriveBits"] throws SyntaxError.
  return crypto.subtle.importKey("raw", raw as unknown as BufferSource, X25519_ALG, false, []);
}

async function importPrivJwk(jwk: NormalizedX25519Jwk): Promise<CryptoKey> {
  // Re-import every operation with extractable:false so accidental exportKey
  // calls fail (defense in depth). The JWK itself remains readable from IDB.
  return crypto.subtle.importKey(
    "jwk",
    jwk as unknown as JsonWebKey,
    X25519_ALG,
    false,
    ["deriveKey", "deriveBits"],
  );
}

function concatBytes(...parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const p of parts) { out.set(p, off); off += p.length; }
  return out;
}

// ─── AAD builder ─────────────────────────────────────────────────────────────
// Encodes each field as uint16-BE length prefix + bytes. This is
// unambiguous even when fields vary in length, and is deterministic
// regardless of the field values.

const _ENC = new TextEncoder();

function buildAad(fields: (string | Uint8Array)[]): Uint8Array {
  const parts: Uint8Array[] = [];
  for (const f of fields) {
    const bytes = typeof f === "string" ? _ENC.encode(f) : f;
    const hdr = new Uint8Array(2);
    new DataView(hdr.buffer).setUint16(0, bytes.length, false);
    parts.push(hdr, bytes);
  }
  return concatBytes(...parts);
}

function uint32BeBytes(n: number): Uint8Array {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n, false);
  return b;
}

async function deriveAesKeyViaHkdf(
  sharedSecret: ArrayBuffer,
  hkdfSalt: Uint8Array,
  info: Uint8Array,
  usage: KeyUsage,
): Promise<CryptoKey> {
  const hkdfKey = await crypto.subtle.importKey(
    "raw", sharedSecret, "HKDF", false, ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: hkdfSalt as unknown as BufferSource,
      info: info as unknown as BufferSource,
    },
    hkdfKey,
    { name: "AES-GCM", length: 256 },  // length:256 REQUIRED — never omit
    false,
    [usage],
  );
}

export async function sealForRecipient(
  plaintext: string,
  recipientEnv: PublicKeyEnvelope,
  senderSignPrivJwk?: NormalizedEd25519Jwk,
  senderSignPubRaw?: Uint8Array,
): Promise<PublicKeySealedPayload> {
  if (recipientEnv.schema !== "yu://key/1" || recipientEnv.alg !== "x25519") {
    throw new Error("invalid recipient key envelope");
  }
  const recipientPubRaw = base64UrlToBytes(recipientEnv.pub);
  const recipientPub = await importEphemeralPub(recipientPubRaw);

  const ephKp = (await crypto.subtle.generateKey(
    X25519_ALG, true, ["deriveBits"],
  )) as CryptoKeyPair;
  const ephemeralPubRaw = new Uint8Array(await crypto.subtle.exportKey("raw", ephKp.publicKey));

  const sharedSecret = await crypto.subtle.deriveBits(
    { name: "X25519", public: recipientPub } as unknown as AlgorithmIdentifier,
    ephKp.privateKey,
    256,
  );

  const hkdfSalt = randomBytes(32);
  const info = concatBytes(
    new TextEncoder().encode(HKDF_INFO_BASE),
    ephemeralPubRaw,
    recipientPubRaw,
  );
  const aesKey = await deriveAesKeyViaHkdf(sharedSecret, hkdfSalt, info, "encrypt");

  const iv = randomBytes(12);
  const aadBytes = buildAad([
    "yu://seal/1",
    "x25519-hkdf-sha256-aes-256-gcm",
    ephemeralPubRaw,
    hkdfSalt,
    iv,
  ]);
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: iv as unknown as BufferSource, additionalData: aadBytes as unknown as BufferSource },
      aesKey,
      new TextEncoder().encode(plaintext) as unknown as BufferSource,
    ),
  );
  const payload: PublicKeySealedPayload = {
    schema: "yu://seal/1",
    alg: "x25519-hkdf-sha256-aes-256-gcm",
    ephemeral_pub: bytesToBase64Url(ephemeralPubRaw),
    hkdf_salt: bytesToBase64Url(hkdfSalt),
    iv: bytesToBase64Url(iv),
    ciphertext: bytesToBase64Url(ciphertext),
    aad: 1,
  };
  if (senderSignPrivJwk && senderSignPubRaw) {
    const sig = await signWithEd25519(senderSignPrivJwk, ciphertext);
    payload.sender_sign_pub = bytesToBase64Url(senderSignPubRaw);
    payload.sender_sig = bytesToBase64Url(sig);
  }
  return payload;
}

export async function openWithPrivateKey(
  payload: PublicKeySealedPayload,
  ownPrivJwk: NormalizedX25519Jwk,
  ownPubRaw: Uint8Array,
): Promise<{plaintext: string; sender: SenderVerification}> {
  if (payload.schema !== "yu://seal/1") throw new Error("unsupported schema");
  if (payload.alg !== "x25519-hkdf-sha256-aes-256-gcm") {
    throw new Error("unsupported alg");
  }
  const ephemeralPubRaw = base64UrlToBytes(payload.ephemeral_pub);
  const ephPub = await importEphemeralPub(ephemeralPubRaw);
  const ownPriv = await importPrivJwk(ownPrivJwk);

  const sharedSecret = await crypto.subtle.deriveBits(
    { name: "X25519", public: ephPub } as unknown as AlgorithmIdentifier,
    ownPriv,
    256,
  );

  const hkdfSalt = base64UrlToBytes(payload.hkdf_salt);
  const info = concatBytes(
    new TextEncoder().encode(HKDF_INFO_BASE),
    ephemeralPubRaw,
    ownPubRaw,
  );
  const aesKey = await deriveAesKeyViaHkdf(sharedSecret, hkdfSalt, info, "decrypt");

  const iv = base64UrlToBytes(payload.iv);
  const ciphertext = base64UrlToBytes(payload.ciphertext);
  const gcmParams: AesGcmParams = { name: "AES-GCM", iv: iv as unknown as BufferSource };
  if (payload.aad === 1) {
    gcmParams.additionalData = buildAad([
      payload.schema,
      payload.alg,
      ephemeralPubRaw,
      hkdfSalt,
      iv,
    ]) as unknown as BufferSource;
  }
  const plainBuf = await crypto.subtle.decrypt(gcmParams, aesKey, ciphertext as unknown as BufferSource);
  const plaintext = new TextDecoder().decode(plainBuf);

  let sender: SenderVerification = { status: "unverified", fingerprint: null };
  if (payload.sender_sign_pub && payload.sender_sig) {
    try {
      const signPubRaw = base64UrlToBytes(payload.sender_sign_pub);
      const sig = base64UrlToBytes(payload.sender_sig);
      const valid = await verifyWithEd25519(signPubRaw, sig, ciphertext);
      if (valid) {
        sender = {
          status: "verified",
          fingerprint: await publicKeyFingerprint(signPubRaw),
        };
      }
    } catch {
      // Malformed sig fields — treat as unverified rather than throwing
    }
  }
  return { plaintext, sender };
}

// ─── Private key export/import (passphrase-wrapped JWK file) ───────────────

export interface PrivKeyExportFile {
  schema: "yu://privkey-export/1";
  alg: "pbkdf2-sha256-aes-256-gcm";
  pbkdf2_salt: string;
  pbkdf2_iterations: number;
  iv: string;
  ciphertext: string;
  /** Ed25519 signing key, AES-GCM encrypted with the same derived key (v1.1+). */
  sign_iv?: string;
  sign_ciphertext?: string;
}

export async function exportPrivateKey(
  privJwk: NormalizedX25519Jwk,
  passphrase: string,
  signPrivJwk?: NormalizedEd25519Jwk,
): Promise<PrivKeyExportFile> {
  if (passphrase.length < 12) {
    throw new Error("passphrase must be at least 12 characters");
  }
  const salt = randomBytes(16);
  const iv = randomBytes(12);
  const aesKey = await deriveAesKeyFromPassphrase(passphrase, salt, PBKDF2_ITERATIONS, "encrypt");
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: iv as unknown as BufferSource },
      aesKey,
      new TextEncoder().encode(JSON.stringify(privJwk)) as unknown as BufferSource,
    ),
  );
  const file: PrivKeyExportFile = {
    schema: "yu://privkey-export/1",
    alg: "pbkdf2-sha256-aes-256-gcm",
    pbkdf2_salt: bytesToBase64Url(salt),
    pbkdf2_iterations: PBKDF2_ITERATIONS,
    iv: bytesToBase64Url(iv),
    ciphertext: bytesToBase64Url(ciphertext),
  };
  if (signPrivJwk) {
    const signIv = randomBytes(12);
    const signCiphertext = new Uint8Array(
      await crypto.subtle.encrypt(
        { name: "AES-GCM", iv: signIv as unknown as BufferSource },
        aesKey,
        new TextEncoder().encode(JSON.stringify(signPrivJwk)) as unknown as BufferSource,
      ),
    );
    file.sign_iv = bytesToBase64Url(signIv);
    file.sign_ciphertext = bytesToBase64Url(signCiphertext);
  }
  return file;
}

export interface ImportPrivateKeyResult {
  privJwk: NormalizedX25519Jwk;
  signPrivJwk?: NormalizedEd25519Jwk | undefined;
}

export async function importPrivateKey(
  file: PrivKeyExportFile,
  passphrase: string,
): Promise<ImportPrivateKeyResult> {
  if (file.schema !== "yu://privkey-export/1") {
    throw new Error("invalid export file schema");
  }
  if (file.alg !== "pbkdf2-sha256-aes-256-gcm") {
    throw new Error("unsupported export alg");
  }
  const salt = base64UrlToBytes(file.pbkdf2_salt);
  const iv = base64UrlToBytes(file.iv);
  const ciphertext = base64UrlToBytes(file.ciphertext);
  const iterations = file.pbkdf2_iterations || PBKDF2_ITERATIONS;
  if (iterations > PBKDF2_MAX_ITERATIONS) {
    throw new Error(`pbkdf2_iterations exceeds maximum (${PBKDF2_MAX_ITERATIONS})`);
  }
  const aesKey = await deriveAesKeyFromPassphrase(passphrase, salt, iterations, "decrypt");
  const plainBuf = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: iv as unknown as BufferSource },
    aesKey,
    ciphertext as unknown as BufferSource,
  );
  const privJwk = normalizeJwk(JSON.parse(new TextDecoder().decode(plainBuf)));
  // Decrypt Ed25519 signing key if present (v1.1+).
  let signPrivJwk: NormalizedEd25519Jwk | undefined;
  if (file.sign_iv && file.sign_ciphertext) {
    const signIv = base64UrlToBytes(file.sign_iv);
    const signCiphertext = base64UrlToBytes(file.sign_ciphertext);
    const signPlainBuf = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: signIv as unknown as BufferSource },
      aesKey,
      signCiphertext as unknown as BufferSource,
    );
    signPrivJwk = JSON.parse(new TextDecoder().decode(signPlainBuf)) as NormalizedEd25519Jwk;
  }
  return { privJwk, signPrivJwk };
}
