// ==========================================================================
// sw.js — Custom Workbox Service Worker
// --------------------------------------------------------------------------
// Injected as the PWA service worker (via vite-plugin-pwa `injectManifest`).
// Responsibilities:
//   1. Precache the lightweight app shell for offline launch.
//   2. Runtime-cache GET navigations (network-first, cache fallback).
//   3. Background Sync: transparently retry POSTed feedback that failed while
//      the device was offline, using Workbox's BackgroundSyncPlugin queue.
//
// Note: the app-level IndexedDB queue (offlineQueue.js) and this SW-level
// BackgroundSync queue are complementary — the former guarantees the payload
// survives even before a request is attempted; the latter auto-replays any
// request that reached the network layer but failed.
// ==========================================================================

import { precacheAndRoute } from "workbox-precaching";
import { registerRoute, NavigationRoute } from "workbox-routing";
import { NetworkFirst, StaleWhileRevalidate } from "workbox-strategies";
import { BackgroundSyncPlugin } from "workbox-background-sync";

// `self.__WB_MANIFEST` is replaced at build time with the precache manifest.
precacheAndRoute(self.__WB_MANIFEST || []);

// --- App-shell navigations: network-first, fall back to cached shell -------
registerRoute(
  new NavigationRoute(
    new NetworkFirst({
      cacheName: "app-shell",
      networkTimeoutSeconds: 4,
    })
  )
);

// --- Static assets (js/css/svg): serve fast, refresh in background ---------
registerRoute(
  ({ request }) =>
    ["script", "style", "image"].includes(request.destination),
  new StaleWhileRevalidate({ cacheName: "static-assets" })
);

// --- Background Sync queue for failed feedback POSTs -----------------------
const feedbackSyncPlugin = new BackgroundSyncPlugin("feedback-sync-queue", {
  maxRetentionTime: 24 * 60, // retry for up to 24 hours (minutes)
});

registerRoute(
  ({ url, request }) =>
    request.method === "POST" && url.pathname.endsWith("/feedback"),
  new NetworkFirst({
    cacheName: "feedback-api",
    plugins: [feedbackSyncPlugin],
  }),
  "POST"
);

// Activate a new SW immediately so offline fixes ship without a reload gap.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) =>
  event.waitUntil(self.clients.claim())
);
