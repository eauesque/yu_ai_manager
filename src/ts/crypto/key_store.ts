/**
 * key_store.ts — IndexedDB layer for the X25519 keypair.
 *
 * Stores JWK objects (not CryptoKey). Working CryptoKey instances are
 * re-imported with extractable: false on every operation in subtle_ops.ts.
 *
 * Future schema changes use a new DB name ("yu-crypto-v2") rather than
 * an upgrade callback; users manually export-and-reimport. See spec
 * §マイグレーション方針.
 */

import type { NormalizedEd25519Jwk, NormalizedX25519Jwk } from "./subtle_ops";
import { normalizeJwk } from "./subtle_ops";

const DB_NAME = "yu-crypto-v1";
const STORE = "keys";
const KEY_ID = "x25519-main";

export interface StoredKeyRecord {
  pubRaw: string;                    // base64url-nopad X25519 public key
  privJwk: NormalizedX25519Jwk;
  createdAt: string;                 // ISO 8601
  signPubRaw?: string;               // base64url-nopad Ed25519 public key (optional)
  signPrivJwk?: NormalizedEd25519Jwk;
}

export { NormalizedEd25519Jwk };

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function getKey(): Promise<StoredKeyRecord | null> {
  const db = await openDb();
  try {
    return await new Promise<StoredKeyRecord | null>((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).get(KEY_ID);
      req.onsuccess = () => {
        const val = req.result as StoredKeyRecord | undefined;
        if (!val) { resolve(null); return; }
        // Re-normalize on read so any legacy "X-25519" gets cleaned.
        val.privJwk = normalizeJwk(val.privJwk as unknown as JsonWebKey);
        resolve(val);
      };
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

export async function putKey(record: StoredKeyRecord): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(record, KEY_ID);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

export async function deleteKey(): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(KEY_ID);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
