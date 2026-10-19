// ==========================================================================
// FeedbackForm.jsx
// --------------------------------------------------------------------------
// A modern, mobile-first multi-step CAROUSEL wizard for submitting feedback.
// Two animated slides — Service category → Feedback text (with the anonymity
// opt-out) — progress dots, per-step validation gating, swipe navigation, and a
// celebratory confirmation modal that surfaces the AI verdict (incl. the
// Gemini-refinement badge). Submits via `submitFeedback`, which transparently
// queues to IndexedDB when offline.
// ==========================================================================

import { useRef, useState } from "react";
import { submitFeedback } from "../api/client";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CategoryIcon,
  CloudOffIcon,
  SpinnerIcon,
} from "./Icons";

// Categories mirror the backend `ServiceCategory` enum exactly.
const CATEGORIES = [
  "Wi-Fi",
  "Library",
  "Hostel",
  "ICT",
  "Teaching",
  "Registration",
  "Examination",
  "Counseling",
  "Administration",
  "Other",
];

const MIN_FEEDBACK_LEN = 10;
const STEP_COUNT = 2;
// Sentinel identity submitted when a student opts out of attribution. The
// backend stores it verbatim; the dashboard's department $lookup finds no
// match and falls back to "Unknown", so nothing links back to the student.
const ANON_ID = "ANONYMOUS";

// Presentation for each sentiment verdict shown in the confirmation modal.
const SENTIMENT = {
  POSITIVE: { label: "Positive", emoji: "😊", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  NEGATIVE: { label: "Negative", emoji: "😟", cls: "bg-rose-50 text-rose-700 ring-rose-200" },
  NEUTRAL: { label: "Neutral", emoji: "😐", cls: "bg-amber-50 text-amber-700 ring-amber-200" },
};

export default function FeedbackForm({ online, studentId, studentName, department, onQueued }) {
  const [step, setStep] = useState(0);
  const [category, setCategory] = useState("");
  const [customCategory, setCustomCategory] = useState("");
  const [feedback, setFeedback] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null); // truthy => confirmation modal open
  const touchX = useRef(null);

  const stepValid = [category !== "", feedback.trim().length >= MIN_FEEDBACK_LEN];

  const goNext = () => {
    if (step < STEP_COUNT - 1 && stepValid[step]) {
      setError("");
      setStep((s) => s + 1);
    }
  };
  const goBack = () => {
    if (step > 0) {
      setError("");
      setStep((s) => s - 1);
    }
  };

  // Tapping a category selects it and glides to the last step — except for
  // "Other", which reveals a text box on this step. Auto-advancing there would
  // slide the box out of view before it could be typed into.
  const pickCategory = (c) => {
    setCategory(c);
    setError("");
    if (c === "Other") return;
    window.setTimeout(() => setStep((s) => (s === 0 ? 1 : s)), 230);
  };

  const onTouchStart = (e) => {
    touchX.current = e.touches[0].clientX;
  };
  const onTouchEnd = (e) => {
    if (touchX.current == null) return;
    const dx = e.changedTouches[0].clientX - touchX.current;
    touchX.current = null;
    if (dx < -50) goNext();
    else if (dx > 50) goBack();
  };

  const handleSubmit = async () => {
    if (!stepValid[1]) {
      setError(`Please add a little more detail (at least ${MIN_FEEDBACK_LEN} characters).`);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await submitFeedback({
        // Withholding attribution means the matric number never leaves the
        // device — the sentinel is sent in its place, not merely hidden.
        student_id: anonymous ? ANON_ID : studentId,
        // The name is withheld entirely when submitting anonymously — unlike
        // department, a name identifies the person, so it must not be sent.
        student_name: anonymous ? undefined : studentName || undefined,
        // Department is sent even for an anonymous submission: it identifies a
        // cohort rather than a person, and dropping it would make anonymous
        // feedback invisible to the per-department analytics this system exists
        // to produce.
        department: department || undefined,
        category,
        custom_category:
          category === "Other" && customCategory.trim()
            ? customCategory.trim()
            : undefined,
        feedback_text: feedback.trim(),
      });
      if (res.queued) {
        setResult({ queued: true });
        if (typeof onQueued === "function") onQueued();
      } else {
        const s = res.data?.sentiment_analysis;
        setResult({ queued: false, label: s?.label ?? "NEUTRAL", source: s?.source });
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  // "Submit another" — glide back to the start, keeping the student's ID.
  // `anonymous` deliberately persists: clearing it would silently re-attach the
  // matric number to the next submission of someone who chose to withhold it.
  const reset = () => {
    setResult(null);
    setCategory("");
    setCustomCategory("");
    setFeedback("");
    setError("");
    setStep(0);
  };

  const remaining = MIN_FEEDBACK_LEN - feedback.trim().length;

  return (
    <div className="w-full">
      <div className="rounded-3xl bg-white shadow-xl shadow-slate-900/5 ring-1 ring-slate-900/5 p-6 sm:p-7">
        {/* Progress dots */}
        <div className="flex items-center justify-center gap-2">
          {Array.from({ length: STEP_COUNT }).map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === step
                  ? "w-6 bg-black"
                  : i < step
                  ? "w-1.5 bg-slate-300"
                  : "w-1.5 bg-slate-200"
              }`}
            />
          ))}
        </div>

        {/* Carousel viewport */}
        <div
          className="overflow-hidden mt-6"
          onTouchStart={onTouchStart}
          onTouchEnd={onTouchEnd}
        >
          <div
            className="flex transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
            style={{ transform: `translateX(-${step * 100}%)` }}
          >
            {/* Step 1 — Category */}
            <Panel active={step === 0}>
              <StepHeading emoji="🎯" title="What's this about?" subtitle="Pick the service you're reviewing." />
              {/* Two columns on a phone, four from `sm` up. */}
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                {CATEGORIES.map((c) => {
                  const selected = category === c;
                  return (
                    <button
                      key={c}
                      type="button"
                      tabIndex={step === 0 ? 0 : -1}
                      onClick={() => pickCategory(c)}
                      aria-pressed={selected}
                      className={`flex min-w-0 items-center gap-2.5 rounded-2xl border px-3 py-3 text-left
                        transition-all active:scale-[0.98] ${
                          selected
                            ? "border-black bg-slate-100 ring-2 ring-slate-300"
                            : "border-slate-200 bg-white hover:border-slate-300"
                        }`}
                    >
                      <span
                        className={`grid place-items-center w-9 h-9 rounded-xl shrink-0 ${
                          selected ? "bg-black text-white" : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        <CategoryIcon name={c} className="w-5 h-5" />
                      </span>
                      {/* `min-w-0` lets this shrink below its intrinsic width —
                          without it a long single word like "Administration"
                          holds the span open and spills outside the card. */}
                      <span className="min-w-0 break-words text-sm font-medium leading-tight text-slate-800">
                        {c}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Picking "Other" lets the student name the service themselves. */}
              {category === "Other" && (
                <div className="mt-3">
                  <label
                    htmlFor="custom_category"
                    className="block text-sm font-medium text-slate-700"
                  >
                    What is it about?
                  </label>
                  <input
                    id="custom_category"
                    type="text"
                    autoComplete="off"
                    maxLength={120}
                    tabIndex={step === 0 ? 0 : -1}
                    value={customCategory}
                    onChange={(e) => setCustomCategory(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        goNext();
                      }
                    }}
                    placeholder="e.g. Transport, Security, Cafeteria…"
                    className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5
                               text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-900"
                  />
                  <p className="mt-1.5 text-xs text-slate-400">
                    Optional — leave blank and it stays as “Other”.
                  </p>
                </div>
              )}
            </Panel>

            {/* Step 2 — Feedback text */}
            <Panel active={step === 1}>
              <StepHeading emoji="✍️" title="Tell us more" subtitle="What happened? Be as honest as you like." />
              <label htmlFor="feedback_text" className="sr-only">
                Your feedback
              </label>
              <textarea
                id="feedback_text"
                rows={5}
                tabIndex={step === 1 ? 0 : -1}
                maxLength={5000}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Describe your experience with this service…"
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5
                           text-slate-900 placeholder-slate-400 resize-y focus:outline-none focus:border-slate-900"
              />
              <div className="mt-1.5 flex items-center justify-between text-xs">
                <span className={remaining > 0 ? "text-slate-400" : "text-emerald-600"}>
                  {remaining > 0 ? `${remaining} more character${remaining === 1 ? "" : "s"} to go` : "Looks good ✓"}
                </span>
                <span className="text-slate-400">{feedback.length}/5000</span>
              </div>

              {/* Anonymity opt-out — withholds the matric number entirely. */}
              <label
                className={`mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border p-3
                  transition-colors ${
                    anonymous
                      ? "border-black bg-slate-100"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
              >
                <input
                  type="checkbox"
                  tabIndex={step === 1 ? 0 : -1}
                  checked={anonymous}
                  onChange={(e) => {
                    setAnonymous(e.target.checked);
                    setError("");
                  }}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-black
                             accent-black focus:ring-0"
                />
                <span className="text-sm">
                  <span className="font-medium text-slate-800">Submit anonymously</span>
                  <span className="block text-xs text-slate-500">
                    {anonymous
                      ? "Your matric number will not be sent or stored."
                      : "Hide my identity — my matric number won't be sent or stored."}
                  </span>
                </span>
              </label>
            </Panel>
          </div>
        </div>

        {error && (
          <p role="alert" className="mt-3 text-sm text-rose-600">
            {error}
          </p>
        )}

        {/* Navigation */}
        <div className="mt-6 flex items-center gap-3">
          {step > 0 && (
            <button
              type="button"
              onClick={goBack}
              className="inline-flex items-center gap-1.5 rounded-2xl px-4 py-3.5 font-medium
                         text-slate-600 hover:bg-slate-100 transition"
            >
              <ArrowLeftIcon className="w-4 h-4" />
              Back
            </button>
          )}

          {step < STEP_COUNT - 1 ? (
            <button
              type="button"
              onClick={goNext}
              disabled={!stepValid[step]}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-2xl px-5 py-3.5
                         font-semibold text-white bg-black
                         shadow-lg shadow-black/20 disabled:opacity-50 disabled:shadow-none
                         transition active:scale-[0.98]"
            >
              Next
              <ArrowRightIcon className="w-4 h-4" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting || !stepValid[1]}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-2xl px-5 py-3.5
                         font-semibold text-white bg-black
                         shadow-lg shadow-black/20 disabled:opacity-50 disabled:shadow-none
                         transition active:scale-[0.98]"
            >
              {submitting ? <SpinnerIcon className="w-4 h-4" /> : null}
              {submitting ? "Submitting…" : online ? "Submit feedback" : "Save offline"}
            </button>
          )}
        </div>
      </div>

      {result && <ConfirmationModal result={result} onClose={reset} />}
    </div>
  );
}

function Panel({ active, children }) {
  return (
    <div
      className={`w-full shrink-0 px-0.5 ${active ? "" : "pointer-events-none"}`}
    >
      {children}
    </div>
  );
}

function StepHeading({ emoji, title, subtitle }) {
  return (
    <div className="mb-4">
      <div className="text-2xl leading-none">{emoji}</div>
      <h2 className="mt-1.5 text-xl font-bold tracking-tight text-slate-900">{title}</h2>
      <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
    </div>
  );
}

function ConfirmationModal({ result, onClose }) {
  const queued = result.queued;
  const sentiment = queued ? null : SENTIMENT[result.label] || SENTIMENT.NEUTRAL;
  const refined = result.source === "gemini";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        className="relative w-full max-w-sm rounded-3xl bg-white p-7 text-center
                   shadow-2xl animate-pop-in"
      >
        <div
          className={`mx-auto grid place-items-center w-16 h-16 rounded-full animate-ring-pop ${
            queued ? "bg-amber-100" : "bg-emerald-100"
          }`}
        >
          {queued ? (
            <CloudOffIcon className="w-8 h-8 text-amber-600" />
          ) : (
            <svg
              className="w-8 h-8 text-emerald-600"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path className="check-path" d="M20 6 9 17l-5-5" />
            </svg>
          )}
        </div>

        <h3 className="mt-4 text-xl font-bold text-slate-900">
          {queued ? "Saved offline" : "Thank you!"}
        </h3>

        {queued ? (
          <p className="mt-2 text-sm text-slate-500">
            You're offline right now — we've saved your feedback and it will send automatically
            once you're back online.
          </p>
        ) : (
          <>
            <p className="mt-2 text-sm text-slate-500">Received and analyzed as:</p>
            <div
              className={`mt-3 inline-flex items-center gap-2 rounded-full px-4 py-1.5 ring-1 ${sentiment.cls}`}
            >
              <span>{sentiment.emoji}</span>
              <span className="font-semibold">{sentiment.label}</span>
            </div>
            {refined && (
              <div className="mt-2 text-xs font-medium text-slate-600">
                ✨ nuance refined by Gemini
              </div>
            )}
          </>
        )}

        <button
          type="button"
          onClick={onClose}
          className="mt-6 w-full rounded-2xl px-5 py-3 font-semibold text-white
                     bg-black active:scale-[0.98] transition"
        >
          Submit another
        </button>
      </div>
    </div>
  );
}
