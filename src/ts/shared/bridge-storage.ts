/**
 * shared/bridge-storage.ts
 *
 * Async storage backed by IndexedDB for large Bridge payloads (prompt + image),
 * with a transparent localStorage fallback so callers don't need to care which
 * backend handled the value.
 *
 * Why IDB: localStorage caps at ~5 MB per origin, which is too tight for high-
 * resolution img2img source images (multi-megapixel PNGs comfortably exceed it
 * after base64 inflation). IDB has no practical cap for our payload sizes.
 *
 * Why a localStorage fallback: a Safari Private Browsing or older browser may
 * fail to open IDB. We degrade to the previous behaviour rather than break the
 * send-to-bridge flow.
 *
 * The API is exposed on window.bridgeStorage so the Bridge inline scripts
 * (vanilla ES5, no module imports) can call it after the bundled script loads.
 */

const DB_NAME = 'yu_ai_manager_bridge';
const DB_VERSION = 1;
const STORE = 'payloads';

let _dbPromise: Promise<IDBDatabase | null> | null = null;

function _openDb(): Promise<IDBDatabase | null> {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve) => {
    let req: IDBOpenDBRequest;
    try {
      req = indexedDB.open(DB_NAME, DB_VERSION);
    } catch {
      resolve(null);
      return;
    }
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(null);
    req.onblocked = () => resolve(null);
  });
  return _dbPromise;
}

async function _idbSet(key: string, value: unknown): Promise<boolean> {
  const db = await _openDb();
  if (!db) return false;
  return new Promise<boolean>((resolve) => {
    try {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(value, key);
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => resolve(false);
      tx.onabort = () => resolve(false);
    } catch {
      resolve(false);
    }
  });
}

async function _idbGet(key: string): Promise<unknown | undefined> {
  const db = await _openDb();
  if (!db) return undefined;
  return new Promise<unknown | undefined>((resolve) => {
    try {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(undefined);
    } catch {
      resolve(undefined);
    }
  });
}

async function _idbDelete(key: string): Promise<void> {
  const db = await _openDb();
  if (!db) return;
  return new Promise<void>((resolve) => {
    try {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
      tx.onabort = () => resolve();
    } catch {
      resolve();
    }
  });
}

export interface BridgeStorage {
  /**
   * Store a JSON-serialisable value. Returns true on success (IDB or
   * localStorage), false if both backends failed (typically a quota error
   * on the localStorage fallback path).
   */
  set(key: string, value: unknown): Promise<boolean>;

  /**
   * Read a value previously stored with set(). Returns undefined when no
   * value is present in either backend. Tries IDB first, then falls back
   * to localStorage so payloads stashed by older versions are still
   * readable (one-cycle backward-compat shim).
   */
  get(key: string): Promise<unknown | undefined>;

  /**
   * Remove a value from both backends. Idempotent.
   */
  remove(key: string): Promise<void>;
}

const bridgeStorage: BridgeStorage = {
  async set(key, value) {
    if (await _idbSet(key, value)) return true;
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch {
      return false;
    }
  },
  async get(key) {
    const v = await _idbGet(key);
    if (v !== undefined) return v;
    // Backward-compat: legacy senders wrote JSON strings to localStorage
    try {
      const raw = localStorage.getItem(key);
      if (raw == null) return undefined;
      try { return JSON.parse(raw); } catch { return raw; }
    } catch {
      return undefined;
    }
  },
  async remove(key) {
    await _idbDelete(key);
    try { localStorage.removeItem(key); } catch { /* ignore */ }
  },
};

(window as any).bridgeStorage = bridgeStorage;

export { bridgeStorage };
