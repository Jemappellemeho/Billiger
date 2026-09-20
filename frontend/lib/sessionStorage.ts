import { Session } from "./accountApi";

const STORAGE_KEY = "billiger:session";

function storageAvailable(): boolean {
  return typeof window !== "undefined" && "localStorage" in window;
}

/** A missing, corrupted or malformed value means "signed out", never an error. */
export function loadSession(): Session | null {
  if (!storageAvailable()) return null;

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.token === "string" && typeof parsed?.email === "string") {
      return { token: parsed.token, email: parsed.email };
    }
    return null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session): void {
  if (!storageAvailable()) return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  if (!storageAvailable()) return;
  window.localStorage.removeItem(STORAGE_KEY);
}
