const PROFILE_KEY = "ifas.student_profile";

export function loadStudentProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;

    const profile = JSON.parse(raw);
    if (
      typeof profile?.fullName !== "string" ||
      typeof profile?.matricNumber !== "string" ||
      !profile.fullName.trim() ||
      !profile.matricNumber.trim()
    ) {
      return null;
    }
    return {
      fullName: profile.fullName.trim(),
      matricNumber: profile.matricNumber.trim(),
      // Department was added after the first release, so a profile saved by an
      // older build will not have it. Default to "" rather than rejecting the
      // profile outright — that would log the student out for no good reason.
      department:
        typeof profile.department === "string" ? profile.department.trim() : "",
    };
  } catch {
    return null;
  }
}

export function saveStudentProfile(profile) {
  const normalized = {
    fullName: profile.fullName.trim(),
    matricNumber: profile.matricNumber.trim(),
    department: (profile.department ?? "").trim(),
  };
  localStorage.setItem(PROFILE_KEY, JSON.stringify(normalized));
  return normalized;
}

export function clearStudentProfile() {
  localStorage.removeItem(PROFILE_KEY);
}
