import axios from "axios";
import {
  enqueueFeedback,
  getQueuedFeedback,
  markAttempt,
  removeQueued,
} from "../db/offlineQueue";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export const api = axios.create({
  baseURL: BASE_URL,
  // A submission that triggers the backend's Tier-B → Gemini escalation can take
  // up to ~8s (the escalation cap) plus model + network time. Keep this well
  // above that so a slow-but-successful analysis isn't misread as "offline" and
  // re-queued (which would duplicate a submission the backend already stored).
  timeout: 20000,
  headers: { "Content-Type": "application/json" },
});


export async function submitFeedback(payload) {
  if (!navigator.onLine) {
    await enqueueFeedback(payload);
    return { queued: true };
  }

  try {
    const { data } = await api.post("/feedback", payload);
    return { queued: false, data };
  } catch (err) {
    // Network-level failure (not a 4xx) → queue for background retry.
    if (!err.response) {
      await enqueueFeedback(payload);
      return { queued: true };
    }
    throw err; // genuine validation/server error — surface to the caller
  }
}

export async function flushQueue() {
  const items = await getQueuedFeedback();
  let sent = 0;
  let failed = 0;

  for (const item of items) {
    try {
      await api.post("/feedback", item.payload);
      await removeQueued(item.queue_id);
      sent += 1;
    } catch (err) {
      await markAttempt(item.queue_id);
      failed += 1;
      // Stop early on a hard network drop; retry on the next heartbeat.
      if (!err.response) break;
    }
  }

  return { sent, failed };
}
