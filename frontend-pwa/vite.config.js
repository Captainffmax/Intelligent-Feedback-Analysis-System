import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// ==========================================================================
// Vite configuration — Student Feedback Ingestion PWA
// --------------------------------------------------------------------------
// Uses `injectManifest` so we ship a CUSTOM Workbox service worker
// (src/sw.js) that owns the offline queue + background-sync behaviour
// rather than an auto-generated one. Kept lean for low-bandwidth campus
// networks: no vendored fonts, no image assets.
// ==========================================================================
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.js",
      registerType: "autoUpdate",
      injectRegister: null, // we register manually in registerSW.js
      devOptions: {
        enabled: true,
        type: "module",
      },
      manifest: {
        name: "Academic Feedback",
        short_name: "Feedback",
        description:
          "Submit feedback on campus academic services — works offline.",
        theme_color: "#4f46e5",
        background_color: "#f8fafc",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        // Inline SVG-based icons only — no heavy raster assets.
        icons: [
          {
            src: "/icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any maskable",
          },
        ],
      },
      injectManifest: {
        // Include woff2 so the self-hosted Outfit font is precached for offline.
        globPatterns: ["**/*.{js,css,html,svg,woff2}"],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      // Dev convenience: forward API calls to the FastAPI backend.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // The connectivity heartbeat (useNetworkStatus) probes the backend's
      // root-level /health; proxy it too so "online" detection works in dev.
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "es2018",
    sourcemap: false,
  },
});
