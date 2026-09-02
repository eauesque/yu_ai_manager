/**
 * idb-store.ts — IndexedDB wrapper (no external libraries)
 *
 * Stores and retrieves API response cache in IndexedDB.
 * Each function fails silently when IndexedDB is unavailable.
 */

const DB_NAME = "yu_ai_cache";
const DB_VERSION = 1;
const STORE_NAME = "api_cache";
/** Maximum number of cache entries to keep */
const MAX_ENTRIES = 500;
/** Absolute maximum age of entries (24 hours) */
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

/** Cache entry type definition */
export interface CacheEntry {
  /** Primary key (request URL) */
  url: string;
  /** Response JSON data */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
  /** Stored timestamp (Date.now()) */
  timestamp: number;
  /** Time-to-live (milliseconds) */
  ttl: number;
}

/** Module-level cached DB connection */
let _dbPromise: Promise<IDBDatabase> | null = null;

/**
 * Open IndexedDB and cache the connection.
 * Returns the same Promise on subsequent calls.
 */
export function openCacheDb(): Promise<IDBDatabase> {
  if (_dbPromise) return _dbPromise;

  _dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
    try {
      const req = indexedDB.open(DB_NAME, DB_VERSION);

      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: "url" });
          store.createIndex("by_timestamp", "timestamp", { unique: false });
        }
      };

      req.onsuccess = () => resolve(req.result);
      req.onerror = () => {
        _dbPromise = null;
        reject(req.error);
      };
    } catch (e) {
      _dbPromise = null;
      reject(e);
    }
  });

  // Clear cached connection when DB is closed
  _dbPromise.then((db) => {
    db.onclose = () => { _dbPromise = null; };
  }).catch(() => {});

  return _dbPromise;
}

/**
 * Retrieve a cache entry for the given URL.
 * Returns null if expired or not found.
 */
export async function getCacheEntry(url: string): Promise<CacheEntry | null> {
  try {
    const db = await openCacheDb();
    return new Promise<CacheEntry | null>((resolve) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const store = tx.objectStore(STORE_NAME);
      const req = store.get(url);
      req.onsuccess = () => {
        const entry = req.result as CacheEntry | undefined;
        if (!entry) { resolve(null); return; }
        const now = Date.now();
        // TTL expired or absolute max age exceeded
        if (now > entry.timestamp + entry.ttl || now > entry.timestamp + MAX_AGE_MS) {
          resolve(null);
          return;
        }
        resolve(entry);
      };
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

/**
 * Save a cache entry (upsert).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function putCacheEntry(url: string, data: any, ttl: number): Promise<void> {
  try {
    const db = await openCacheDb();
    const entry: CacheEntry = { url, data, timestamp: Date.now(), ttl };
    return new Promise<void>((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      store.put(entry);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Silently ignore when IndexedDB is unavailable
  }
}

/**
 * Delete the cache entry for the given URL.
 */
export async function deleteCacheEntry(url: string): Promise<void> {
  try {
    const db = await openCacheDb();
    return new Promise<void>((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      store.delete(url);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Silently ignore
  }
}

/**
 * Delete all cache entries.
 */
export async function clearAllCache(): Promise<void> {
  try {
    const db = await openCacheDb();
    return new Promise<void>((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      store.clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  } catch {
    // Silently ignore
  }
}

/**
 * Delete expired entries and remove oldest entries exceeding MAX_ENTRIES.
 * @returns Number of deleted entries
 */
export async function purgeExpiredEntries(): Promise<number> {
  try {
    const db = await openCacheDb();
    return new Promise<number>((resolve) => {
      const now = Date.now();
      let purged = 0;

      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);

      // Iterate all entries: delete expired ones, collect remaining
      const allEntries: CacheEntry[] = [];
      const cursorReq = store.openCursor();

      cursorReq.onsuccess = () => {
        const cursor = cursorReq.result;
        if (cursor) {
          const entry = cursor.value as CacheEntry;
          if (now > entry.timestamp + entry.ttl || now > entry.timestamp + MAX_AGE_MS) {
            cursor.delete();
            purged++;
          } else {
            allEntries.push(entry);
          }
          cursor.continue();
        } else {
          // Cursor scan complete — delete oldest entries exceeding MAX_ENTRIES
          if (allEntries.length > MAX_ENTRIES) {
            allEntries.sort((a, b) => a.timestamp - b.timestamp);
            const excess = allEntries.length - MAX_ENTRIES;
            for (let i = 0; i < excess; i++) {
              store.delete(allEntries[i].url);
              purged++;
            }
          }
        }
      };

      tx.oncomplete = () => resolve(purged);
      tx.onerror = () => resolve(purged);
    });
  } catch {
    return 0;
  }
}
