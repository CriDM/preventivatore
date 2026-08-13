/**
 * Preventivatore - Offline Data Store & Sync Manager (IndexedDB)
 */

const DB_NAME = 'PreventivatoreDB';
const DB_VERSION = 1;

function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('quotes')) {
        db.createObjectStore('quotes', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('customers')) {
        db.createObjectStore('customers', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('products')) {
        db.createObjectStore('products', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('company')) {
        db.createObjectStore('company', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('sync_queue')) {
        db.createObjectStore('sync_queue', { keyPath: 'queue_id', autoIncrement: true });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

// Generic Store Writers & Readers
async function dbPutItems(storeName, items) {
  try {
    const db = await openDB();
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
    const itemArray = Array.isArray(items) ? items : [items];
    for (const item of itemArray) {
      if (item) store.put(item);
    }
    return new Promise((resolve) => {
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => resolve(false);
    });
  } catch (e) {
    console.error(`[IndexedDB] Error writing to ${storeName}`, e);
    return false;
  }
}

async function dbGetAllItems(storeName) {
  try {
    const db = await openDB();
    const tx = db.transaction(storeName, 'readonly');
    const store = tx.objectStore(storeName);
    const request = store.getAll();
    return new Promise((resolve) => {
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => resolve([]);
    });
  } catch (e) {
    console.error(`[IndexedDB] Error reading from ${storeName}`, e);
    return [];
  }
}

async function dbDeleteItem(storeName, key) {
  try {
    const db = await openDB();
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
    store.delete(key);
    return new Promise((resolve) => {
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => resolve(false);
    });
  } catch (e) {
    console.error(`[IndexedDB] Error deleting key ${key} from ${storeName}`, e);
    return false;
  }
}

// --- Specific Store Helpers ---
async function dbSaveQuotes(quotes) {
  return dbPutItems('quotes', quotes);
}

async function dbGetQuotes() {
  const quotes = await dbGetAllItems('quotes');
  // Sort descending by id or quote_number
  return quotes.sort((a, b) => (b.id || 0) - (a.id || 0));
}

async function dbSaveCustomers(customers) {
  return dbPutItems('customers', customers);
}

async function dbGetCustomers() {
  return dbGetAllItems('customers');
}

async function dbSaveProducts(products) {
  return dbPutItems('products', products);
}

async function dbGetProducts() {
  return dbGetAllItems('products');
}

async function dbSaveCompany(company) {
  const comp = { id: 1, ...company };
  return dbPutItems('company', comp);
}

async function dbGetCompany() {
  const list = await dbGetAllItems('company');
  return list.length > 0 ? list[0] : null;
}

// --- Sync Queue Helpers ---
async function dbQueueSyncAction(action) {
  // action = { url, method, payload, meta }
  try {
    const db = await openDB();
    const tx = db.transaction('sync_queue', 'readwrite');
    const store = tx.objectStore('sync_queue');
    const item = {
      ...action,
      created_at: new Date().toISOString()
    };
    store.add(item);
    return new Promise((resolve) => {
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => resolve(false);
    });
  } catch (e) {
    console.error('[SyncQueue] Error adding item to sync queue', e);
    return false;
  }
}

async function dbGetSyncQueue() {
  return dbGetAllItems('sync_queue');
}

async function dbRemoveSyncQueueItem(queue_id) {
  return dbDeleteItem('sync_queue', queue_id);
}

// Automatic Synchronization Engine
let isSyncing = false;

async function syncOfflineQueue(authToken, onSyncCompleteCallback) {
  if (isSyncing || !navigator.onLine) return;
  
  const queue = await dbGetSyncQueue();
  if (!queue || queue.length === 0) return;

  isSyncing = true;
  console.log(`[SyncEngine] Starting offline sync (${queue.length} pending actions)...`);

  let syncedCount = 0;
  const token = authToken || localStorage.getItem('access_token');

  for (const item of queue) {
    try {
      const headers = {
        'Content-Type': 'application/json',
        ...(item.headers || {})
      };
      if (token) {
        headers['Authorization'] = 'Bearer ' + token;
      }

      const options = {
        method: item.method || 'POST',
        headers: headers
      };
      if (item.payload) {
        options.body = typeof item.payload === 'string' ? item.payload : JSON.stringify(item.payload);
      }

      const res = await fetch(item.url, options);

      if (res.ok || res.status === 200 || res.status === 201) {
        await dbRemoveSyncQueueItem(item.queue_id);
        syncedCount++;
      } else if (res.status >= 400 && res.status < 500) {
        // Validation error or bad request: remove from queue to prevent infinite loop
        console.warn(`[SyncEngine] Request failed with status ${res.status}, removing from queue:`, item);
        await dbRemoveSyncQueueItem(item.queue_id);
      }
    } catch (err) {
      console.error(`[SyncEngine] Network error while syncing item ${item.queue_id}:`, err);
      break; // Stop loop if network lost again
    }
  }

  isSyncing = false;

  if (syncedCount > 0) {
    console.log(`[SyncEngine] Successfully synced ${syncedCount} items.`);
    if (typeof onSyncCompleteCallback === 'function') {
      onSyncCompleteCallback(syncedCount);
    }
  }
}

// Window Event Listener for Automatic Reconnect Sync
window.addEventListener('online', () => {
  console.log('[Network] App is back online!');
  const event = new CustomEvent('app-connection-changed', { detail: { online: true } });
  window.dispatchEvent(event);
  
  // Trigger sync
  if (typeof window.triggerGlobalSync === 'function') {
    window.triggerGlobalSync();
  }
});

window.addEventListener('offline', () => {
  console.log('[Network] App is offline.');
  const event = new CustomEvent('app-connection-changed', { detail: { online: false } });
  window.dispatchEvent(event);
});
