// ==========================================================================
// offlineQueue.js
// --------------------------------------------------------------------------
// Client-side durable queue for feedback payloads, backed by IndexedDB
// (via `idb`). When a network heartbeat indicates a dropped connection,
// submissions are intercepted and stashed here, then flushed to the backend
// once connectivity is restored. This keeps the ingestion node usable on
// unstable campus networks.
// ==========================================================================

import { openDB } from "idb";

const DB_NAME = "feedback-ingestion";
const DB_VERSION = 1;
const STORE = "pending_feedback";

// Lazily-created singleton DB promise.
let dbPromise = null;

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, {
            keyPath: "queue_id",
            autoIncrement: true,
          });
          store.createIndex("queued_at", "queued_at");
        }
      },
    });
  }
  return dbPromise;
}

/**
 * Persist a feedback payload for later dispatch.
 * @param {{student_id:string, category:string, feedback_text:string}} payload
 * @returns {Promise<number>} the generated queue_id
 */
export async function enqueueFeedback(payload) {
  const db = await getDB();
  return db.add(STORE, {
    payload,
    queued_at: new Date().toISOString(),
    attempts: 0,
  });
}

/** Return all queued items (oldest first). */
export async function getQueuedFeedback() {
  const db = await getDB();
  return db.getAllFromIndex(STORE, "queued_at");
}

/** Count of pending items — used to badge the UI. */
export async function pendingCount() {
  const db = await getDB();
  return db.count(STORE);
}

/** Remove a successfully-dispatched item. */
export async function removeQueued(queueId) {
  const db = await getDB();
  return db.delete(STORE, queueId);
}

/** Increment the retry counter for an item that failed to send. */
export async function markAttempt(queueId) {
  const db = await getDB();
  const item = await db.get(STORE, queueId);
  if (item) {
    item.attempts = (item.attempts || 0) + 1;
    await db.put(STORE, item);
  }
}
