import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRightIcon,
  CheckIcon,
  CloseIcon,
  CloudOffIcon,
  MenuIcon,
} from "../components/Icons";

export default function HomePage({ profile }) {
  const destination = profile ? "/feedback" : "/profile";
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  return (
    <main className="mx-auto flex w-full max-w-[100rem] flex-1 flex-col px-5 pb-12 pt-7 sm:px-8 sm:pt-10 lg:px-12 xl:px-16">
      {/* Below `sm` the links collapse behind a toggle. They previously sat in a
          horizontally scrolling strip, which on a phone meant half the menu was
          off-screen with nothing to indicate it was there. */}
      <nav className="rounded-2xl border border-slate-200/80 bg-white/75 px-3 py-2 shadow-sm shadow-slate-900/[0.03] backdrop-blur-sm sm:px-4 lg:px-5">
        <div className="flex items-center justify-between gap-3">
          <Brand />

          <div className="hidden items-center gap-1 sm:flex sm:gap-2">
            <NavLinks destination={destination} onNavigate={closeMenu} />
          </div>

          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-controls="primary-menu"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-slate-700 transition hover:bg-slate-100 hover:text-black sm:hidden"
          >
            {menuOpen ? <CloseIcon className="h-5 w-5" /> : <MenuIcon className="h-5 w-5" />}
          </button>
        </div>

        {menuOpen && (
          <div
            id="primary-menu"
            className="mt-2 flex flex-col gap-1 border-t border-slate-200/80 pt-2 sm:hidden"
          >
            <NavLinks destination={destination} onNavigate={closeMenu} stacked />
          </div>
        )}
      </nav>

      <section className="relative mt-10 min-h-[34rem] overflow-hidden rounded-[2.5rem] bg-slate-950 text-white shadow-2xl shadow-black/15 sm:mt-14 lg:min-h-[39rem]">
        <img
          src="/student.jpeg"
          alt="Student carrying books and a backpack on campus"
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-slate-950 via-slate-950/90 to-slate-950/10" />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950/75 via-transparent to-transparent" />
        <div className="absolute right-7 top-7 hidden rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-right backdrop-blur-md sm:block">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">Campus pulse</p>
          <p className="mt-1 text-sm font-medium text-white">Small notes. Real change.</p>
        </div>
        <div className="relative flex min-h-[34rem] flex-col justify-end px-6 py-9 pb-32 sm:min-h-[39rem] sm:px-12 sm:py-12 sm:pb-36 lg:max-w-2xl lg:px-16">
          <h1 className="mt-4 max-w-xl text-4xl font-semibold leading-[1.02] tracking-[-0.05em] sm:text-6xl lg:text-7xl">
            Make campus work better.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-slate-200 sm:text-lg">
            Share what is working, what is getting in the way, and where your
            school can do better. A few honest words can move a service forward.
          </p>
          <Link
            to={destination}
            className="mt-8 inline-flex items-center gap-2 rounded-2xl bg-white px-5 py-3.5 text-sm font-semibold text-slate-950 transition hover:bg-slate-100 active:scale-[0.98]"
          >
            {profile ? "Continue to feedback" : "Share your feedback"}
            <ArrowRightIcon className="h-4 w-4" />
          </Link>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-white/10 px-3 py-1.5 text-xs text-slate-200 backdrop-blur-md">No email required</span>
            <span className="rounded-full bg-white/10 px-3 py-1.5 text-xs text-slate-200 backdrop-blur-md">Works offline</span>
          </div>
        </div>
        <div className="absolute bottom-0 left-0 right-0 grid max-w-2xl grid-cols-3 gap-3 border-t border-white/15 bg-slate-950/25 px-6 py-5 text-xs text-slate-300 backdrop-blur-sm sm:px-12 lg:px-16">
          <div>
            <p className="text-lg font-semibold text-white">01</p>
            <p className="mt-1">Tell us who you are</p>
          </div>
          <div>
            <p className="text-lg font-semibold text-white">02</p>
            <p className="mt-1">Choose a service</p>
          </div>
          <div>
            <p className="text-lg font-semibold text-white">03</p>
            <p className="mt-1">Say what you think</p>
          </div>
        </div>
      </section>

      <section className="mt-8 grid gap-4 sm:grid-cols-3">
        <ValueCard
          icon={<CheckIcon className="h-5 w-5" />}
          title="Straight to the point"
          text="No long forms. Just the details needed to understand your experience."
        />
        <ValueCard
          icon={<CloudOffIcon className="h-5 w-5" />}
          title="Works without data"
          text="Your feedback can be saved offline and sent when your connection returns."
        />
        <ValueCard
          icon={<span className="text-lg">✦</span>}
          title="Read by the right people"
          text="Feedback is grouped by service so recurring issues are easier to act on."
        />
      </section>

      <section
        id="how-it-works"
        className="mt-16 scroll-mt-8 rounded-[2rem] border border-slate-200/80 bg-white p-6 shadow-sm shadow-slate-900/[0.03] sm:mt-24 sm:p-10"
      >
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-black">
            How it works
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            A short path from experience to action.
          </h2>
          <p className="mt-3 text-base leading-7 text-slate-500">
            Pick the service, describe what happened, and send it. The system
            groups feedback by theme so recurring issues are easier to spot.
          </p>
        </div>
        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          <ProcessStep number="01" title="Choose a service" text="Start with Wi-Fi, teaching, registration, or any other service on campus." />
          <ProcessStep number="02" title="Write honestly" text="Tell us what worked, what did not, and what would make the experience better." />
          <ProcessStep number="03" title="Send it" text="Your note is analyzed and added to the feedback picture for administrators." />
        </div>
      </section>

      <section
        id="why-it-matters"
        className="mt-6 grid scroll-mt-8 gap-6 rounded-[2rem] bg-black p-6 text-white shadow-xl shadow-black/10 sm:mt-8 sm:grid-cols-[0.8fr_1.2fr] sm:p-10"
      >
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
            Why it matters
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
            The small details are often the useful ones.
          </h2>
        </div>
        <div className="flex items-end">
          <p className="max-w-xl text-base leading-7 text-slate-300">
            A slow connection, a confusing process, or a helpful staff member
            can be easy to forget once the day moves on. Sharing it gives the
            people responsible for campus services something specific to work
            with—not just a score, but the reason behind it.
          </p>
        </div>
      </section>

      <p className="mt-auto pt-10 text-center text-xs text-slate-400">
        Intelligent Feedback Analysis System · One thoughtful note at a time
      </p>
    </main>
  );
}

// One definition drives both the desktop row and the stacked mobile menu, so
// the two can never drift apart. `stacked` only changes the layout.
function NavLinks({ destination, onNavigate, stacked = false }) {
  const base = stacked
    ? "block rounded-xl px-3 py-2.5 text-sm font-semibold transition"
    : "rounded-xl px-3 py-2 text-xs font-semibold transition";
  const idle = "text-slate-500 hover:bg-slate-100 hover:text-black";
  const active = "bg-slate-100 text-slate-900 hover:bg-slate-200";

  return (
    <>
      <Link to="/" onClick={onNavigate} className={`${base} ${active}`}>
        Home
      </Link>
      <Link to={destination} onClick={onNavigate} className={`${base} ${idle}`}>
        Share feedback
      </Link>
      <a
        href="#how-it-works"
        onClick={onNavigate}
        className={`${base} ${idle} whitespace-nowrap`}
      >
        How it works
      </a>
      <a
        href="#why-it-matters"
        onClick={onNavigate}
        className={`${base} ${idle} whitespace-nowrap`}
      >
        Why it matters
      </a>
    </>
  );
}

function Brand() {
  return (
    <Link to="/" aria-label="Campus Feedback home" className="shrink-0">
      <img
        src="/feedback-logo.png"
        alt="Feedback"
        className="h-16 w-16 object-contain sm:h-20 sm:w-20 lg:h-28 lg:w-28"
      />
    </Link>
  );
}

function ValueCard({ icon, title, text }) {
  return (
    <article className="rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm shadow-slate-900/[0.03]">
      <div className="grid h-10 w-10 place-items-center rounded-2xl bg-slate-100 text-black">
        {icon}
      </div>
      <h2 className="mt-4 text-sm font-semibold text-slate-900">{title}</h2>
      <p className="mt-1.5 text-sm leading-6 text-slate-500">{text}</p>
    </article>
  );
}

function ProcessStep({ number, title, text }) {
  return (
    <article className="rounded-2xl bg-slate-50 p-4">
      <span className="text-xs font-semibold tracking-[0.16em] text-black">{number}</span>
      <h3 className="mt-6 text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mt-1.5 text-sm leading-6 text-slate-500">{text}</p>
    </article>
  );
}
