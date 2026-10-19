import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeftIcon, ArrowRightIcon } from "../components/Icons";
import { saveStudentProfile } from "../profile";

// Offered as autocomplete hints only. The input stays free text so a student
// from a department not listed here can still type their own.
const DEPARTMENT_SUGGESTIONS = [
  "Computer Science",
  "Electrical Engineering",
  "Mathematics",
  "Biology",
  "Chemistry",
  "Physics",
  "Accounting",
  "Business Administration",
  "Economics",
  "Law",
  "Mass Communication",
  "Medicine and Surgery",
  "Nursing",
  "Political Science",
];

export default function ProfilePage({ onComplete }) {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [matricNumber, setMatricNumber] = useState("");
  const [department, setDepartment] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (event) => {
    event.preventDefault();
    const name = fullName.trim();
    const matric = matricNumber.trim();
    const dept = department.trim();
    if (!name || !matric || !dept) {
      setError("Please enter your full name, matric number and department.");
      return;
    }

    const profile = saveStudentProfile({
      fullName: name,
      matricNumber: matric,
      department: dept,
    });
    onComplete(profile);
    navigate("/feedback");
  };

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col px-5 pb-10 pt-7 sm:max-w-xl sm:pt-12 lg:max-w-2xl">
      <Link
        to="/"
        className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-slate-500 transition hover:text-slate-900"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to home
      </Link>

      <div className="mt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-black">
          Before we begin
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
          Tell us who is speaking.
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-500">
          Use your name and matric number once. We will remember them on this
          device so your next piece of feedback starts faster.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="mt-8 rounded-[2rem] bg-white p-6 shadow-xl shadow-slate-900/5 ring-1 ring-slate-900/5 sm:p-7"
      >
        <label htmlFor="full_name" className="block text-sm font-medium text-slate-700">
          Full name
        </label>
        <input
          id="full_name"
          type="text"
          autoComplete="name"
          autoFocus
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          placeholder="e.g. Ada Okafor"
          className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-slate-900 placeholder-slate-400 focus:border-slate-900 focus:outline-none"
        />

        <label htmlFor="matric_number" className="mt-5 block text-sm font-medium text-slate-700">
          Matric number
        </label>
        <input
          id="matric_number"
          type="text"
          autoComplete="off"
          value={matricNumber}
          onChange={(event) => setMatricNumber(event.target.value)}
          placeholder="e.g. 2460141200"
          className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-slate-900 placeholder-slate-400 focus:border-slate-900 focus:outline-none"
        />

        <label htmlFor="department" className="mt-5 block text-sm font-medium text-slate-700">
          Department
        </label>
        <input
          id="department"
          type="text"
          autoComplete="organization"
          list="department-suggestions"
          value={department}
          onChange={(event) => setDepartment(event.target.value)}
          placeholder="e.g. Computer Science"
          className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-slate-900 placeholder-slate-400 focus:border-slate-900 focus:outline-none"
        />
        {/* Suggestions only — the field stays free text so any department works. */}
        <datalist id="department-suggestions">
          {DEPARTMENT_SUGGESTIONS.map((d) => (
            <option key={d} value={d} />
          ))}
        </datalist>
        <p className="mt-1.5 text-xs text-slate-400">
          This groups your feedback by department on the staff dashboard.
        </p>

        {error && (
          <p role="alert" className="mt-3 text-sm text-rose-600">
            {error}
          </p>
        )}

        <button
          type="submit"
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl bg-black px-5 py-3.5 font-semibold text-white shadow-lg shadow-black/20 transition active:scale-[0.98]"
        >
          Continue to feedback
          <ArrowRightIcon className="h-4 w-4" />
        </button>
        <p className="mt-4 text-center text-xs leading-5 text-slate-400">
          No email, password, or verification is required.
        </p>
      </form>
    </main>
  );
}
