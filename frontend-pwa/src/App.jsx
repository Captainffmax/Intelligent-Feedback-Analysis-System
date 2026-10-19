// ==========================================================================
// App.jsx
// --------------------------------------------------------------------------
// Application shell for the Student Feedback PWA. A modern, mobile-first
// layout: a soft gradient canvas, a compact header with a live connectivity
// pill, the carousel feedback wizard, and a list of any offline-saved
// submissions with a manual "Sync now" control. Flushes the queue on reconnect.
// ==========================================================================

import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import FeedbackForm from "./components/FeedbackForm";
import { WifiIcon, CloudOffIcon, SpinnerIcon } from "./components/Icons";
import { useNetworkStatus } from "./hooks/useNetworkStatus";
import { flushQueue } from "./api/client";
import { getQueuedFeedback } from "./db/offlineQueue";
import HomePage from "./pages/HomePage";
import ProfilePage from "./pages/ProfilePage";
import { clearStudentProfile, loadStudentProfile } from "./profile";

export default function App() {
  const [queued, setQueued] = useState([]);
  const [flushing, setFlushing] = useState(false);
  const [profile, setProfile] = useState(loadStudentProfile);
  const pending = queued.length;

  const refreshPending = useCallback(async () => {
    try {
      setQueued(await getQueuedFeedback());
    } catch {
      /* IndexedDB unavailable — ignore */
    }
  }, []);

  // On reconnect (offline -> online transition), flush the queue.
  const handleReconnect = useCallback(async () => {
    setFlushing(true);
    try {
      await flushQueue();
    } finally {
      setFlushing(false);
      refreshPending();
    }
  }, [refreshPending]);

  const online = useNetworkStatus(handleReconnect);

  useEffect(() => {
    refreshPending();
    const t = setInterval(refreshPending, 5000);
    return () => clearInterval(t);
  }, [refreshPending]);

  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-slate-50">
        <div className="flex-1">
          <Routes>
            <Route path="/" element={<HomePage profile={profile} />} />
            <Route
              path="/profile"
              element={<ProfilePage onComplete={setProfile} />}
            />
            <Route
              path="/feedback"
              element={
                profile ? (
                  <FeedbackPage
                    profile={profile}
                    online={online}
                    pending={pending}
                    flushing={flushing}
                    queued={queued}
                    onQueued={refreshPending}
                    onSync={handleReconnect}
                    onLogout={() => {
                      clearStudentProfile();
                      setProfile(null);
                    }}
                  />
                ) : (
                  <Navigate to="/profile" replace />
                )
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
        <footer className="px-4 py-4 text-center text-xs text-slate-400">
          Intelligent Feedback Analysis System · Works offline
        </footer>
      </div>
    </BrowserRouter>
  );
}

function FeedbackPage({ profile, online, pending, flushing, queued, onQueued, onSync, onLogout }) {
  const navigate = useNavigate();
  const handleLogout = () => {
    onLogout();
    navigate("/", { replace: true });
  };

  return (
    <div className="mx-auto w-full max-w-md px-4 pb-10 pt-6 sm:max-w-xl lg:max-w-3xl">
      <header className="mb-6 flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigate("/")}
          className="text-left"
          aria-label="Back to home"
        >
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-black text-sm font-bold text-white">
              IF
            </div>
            <div>
              <div className="text-sm font-bold leading-tight text-slate-900">Campus Feedback</div>
              <div className="text-[11px] leading-tight text-slate-400">
                Hi, {profile.fullName.split(" ")[0]}
              </div>
            </div>
          </div>
        </button>
        <div className="flex items-center gap-2">
          <StatusPill online={online} flushing={flushing} pending={pending} />
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-full px-2.5 py-1 text-xs font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
          >
            Log out
          </button>
        </div>
      </header>

      <FeedbackForm
        online={online}
        studentId={profile.matricNumber}
        studentName={profile.fullName}
        department={profile.department}
        onQueued={onQueued}
      />

      {pending > 0 && (
        <PendingQueue
          items={queued}
          online={online}
          flushing={flushing}
          onSync={onSync}
        />
      )}
    </div>
  );
}

function StatusPill({ online, flushing, pending }) {
  const base = "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium";
  if (!online) {
    return (
      <span className={`${base} bg-amber-100 text-amber-700`}>
        <CloudOffIcon className="w-3.5 h-3.5" /> Offline
      </span>
    );
  }
  if (flushing) {
    return (
      <span className={`${base} bg-slate-200 text-slate-900`}>
        <SpinnerIcon className="w-3.5 h-3.5" /> Syncing
      </span>
    );
  }
  if (pending > 0) {
    return <span className={`${base} bg-slate-200 text-slate-900`}>{pending} pending</span>;
  }
  return (
    <span className={`${base} bg-emerald-100 text-emerald-700`}>
      <WifiIcon className="w-3.5 h-3.5" /> Online
    </span>
  );
}

function PendingQueue({ items, online, flushing, onSync }) {
  const canSync = online && !flushing && items.length > 0;
  return (
    <section className="mt-6" aria-label="Pending offline submissions">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-slate-700">Saved offline ({items.length})</h2>
        <button
          type="button"
          onClick={onSync}
          disabled={!canSync}
          className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium
                     bg-white border border-slate-200 text-slate-600 disabled:opacity-50
                     enabled:hover:bg-slate-50 transition"
        >
          {flushing ? <SpinnerIcon className="w-3.5 h-3.5" /> : null}
          {flushing ? "Syncing…" : online ? "Sync now" : "Waiting for network"}
        </button>
      </div>

      <ul className="space-y-2">
        {items.map((item) => (
          <li
            key={item.queue_id}
            className="rounded-2xl bg-white border border-slate-200 px-3.5 py-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-slate-700">
                {item.payload?.category ?? "Feedback"}
              </span>
              <span className="text-[10px] text-slate-400">
                {formatQueuedAt(item.queued_at)}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-500 line-clamp-2">
              {item.payload?.feedback_text}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatQueuedAt(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}
