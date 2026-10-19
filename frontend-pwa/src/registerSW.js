// ==========================================================================
// registerSW.js
// --------------------------------------------------------------------------
// Registers the custom Workbox service worker (src/sw.js). Kept separate from
// main.jsx so registration concerns stay isolated. Uses the virtual module
// provided by vite-plugin-pwa.
// ==========================================================================

import { registerSW } from "virtual:pwa-register";

export function initServiceWorker() {
  if (!("serviceWorker" in navigator)) return;

  const updateSW = registerSW({
    immediate: true,
    onNeedRefresh() {
      // A new version is available; refresh silently on next load.
      updateSW(true);
    },
    onOfflineReady() {
      // App shell cached — ready to run without a network.
      // eslint-disable-next-line no-console
      console.info("[PWA] Offline-ready: feedback can be submitted offline.");
    },
  });
}
