// ==========================================================================
// useNetworkStatus.js
// --------------------------------------------------------------------------
// Network heartbeat hook. Combines the browser's `online`/`offline` events
// with an active lightweight ping so we detect "connected to Wi-Fi but no
// real internet" situations common on campus networks. Exposes the live
// status and fires a callback on the offline -> online transition so the
// caller can flush the offline queue.
// ==========================================================================

import { useCallback, useEffect, useRef, useState } from "react";

const HEARTBEAT_INTERVAL_MS = 15000;

export function useNetworkStatus(onReconnect) {
  const [online, setOnline] = useState(navigator.onLine);
  const wasOnline = useRef(navigator.onLine);

  // Active heartbeat: HEAD the backend health endpoint to confirm reachability.
  const probe = useCallback(async () => {
    try {
      const base = import.meta.env.VITE_API_BASE_URL || "/api";
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 5000);
      const res = await fetch(`${base.replace(/\/api$/, "")}/health`, {
        method: "GET",
        signal: controller.signal,
        cache: "no-store",
      });
      clearTimeout(timer);
      return res.ok;
    } catch {
      return false;
    }
  }, []);

  const evaluate = useCallback(
    async (fromEvent) => {
      const reachable = fromEvent === "offline" ? false : await probe();
      setOnline(reachable);

      // Detect the offline -> online transition and trigger the flush.
      if (reachable && !wasOnline.current && typeof onReconnect === "function") {
        onReconnect();
      }
      wasOnline.current = reachable;
    },
    [probe, onReconnect]
  );

  useEffect(() => {
    const handleOnline = () => evaluate("online");
    const handleOffline = () => evaluate("offline");

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    // Periodic heartbeat catches silent drops the events miss.
    const interval = setInterval(() => evaluate("heartbeat"), HEARTBEAT_INTERVAL_MS);

    // Initial probe on mount.
    evaluate("heartbeat");

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      clearInterval(interval);
    };
  }, [evaluate]);

  return online;
}
