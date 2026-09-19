const DB_NAME = "voicefield-offline";
const DB_VERSION = 1;

const TABLES = ["jobs", "customers", "quotes", "invoices"];
const SYNC_STORE = "pending-sync";

interface PendingSync {
  id?: number;
  table: string;
  operation: "create" | "update" | "delete";
  data: any;
  timestamp: number;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      for (const table of TABLES) {
        if (!db.objectStoreNames.contains(table)) {
          db.createObjectStore(table, { keyPath: "id" });
        }
      }
      if (!db.objectStoreNames.contains(SYNC_STORE)) {
        const syncStore = db.createObjectStore(SYNC_STORE, {
          keyPath: "id",
          autoIncrement: true,
        });
        syncStore.createIndex("table", "table", { unique: false });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function tx(storeName: string, mode: IDBTransactionMode = "readonly"): Promise<IDBObjectStore> {
  return openDB().then(
    (db) =>
      new Promise<IDBObjectStore>((resolve, reject) => {
        const transaction = db.transaction(storeName, mode);
        const store = transaction.objectStore(storeName);
        resolve(store);
      })
  );
}

function idbRequest<T>(request: IDBRequest): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function saveTable(table: string, data: any[]): Promise<void> {
  const db = await openDB();
  const transaction = db.transaction(table, "readwrite");
  const store = transaction.objectStore(table);
  for (const record of data) {
    store.put(record);
  }
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
}

export async function getTable(table: string): Promise<any[]> {
  const store = await tx(table);
  return idbRequest<any[]>(store.getAll());
}

export async function getRecord(table: string, id: string): Promise<any | undefined> {
  const store = await tx(table);
  return idbRequest<any | undefined>(store.get(id));
}

export async function addPendingSync(
  table: string,
  operation: "create" | "update" | "delete",
  data: any
): Promise<number> {
  const db = await openDB();
  const transaction = db.transaction(SYNC_STORE, "readwrite");
  const store = transaction.objectStore(SYNC_STORE);
  const entry: PendingSync = { table, operation, data, timestamp: Date.now() };
  const request = store.add(entry);
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result as number);
    transaction.onerror = () => reject(transaction.error);
  });
}

export async function getPendingSync(): Promise<PendingSync[]> {
  const store = await tx(SYNC_STORE);
  return idbRequest<PendingSync[]>(store.getAll());
}

export async function clearPendingSync(id: number): Promise<void> {
  const store = await tx(SYNC_STORE, "readwrite");
  const request = store.delete(id);
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

export async function clearTable(table: string): Promise<void> {
  const store = await tx(table, "readwrite");
  const request = store.clear();
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

export type { PendingSync };
