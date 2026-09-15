import { createEmptyState, ShoppingListState } from "./shoppingList";

const STORAGE_KEY = "billiger:shopping-list";

function storageAvailable(): boolean {
  return typeof window !== "undefined" && "localStorage" in window;
}

/**
 * Guest mode (map decision: "rein lokale Speicherung, kein Server-Zugriffspunkt")
 * has no server to fall back on, so a missing/corrupted value degrades to an
 * empty list rather than throwing.
 */
export function loadState(): ShoppingListState {
  if (!storageAvailable()) return createEmptyState();

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return createEmptyState();

  try {
    return JSON.parse(raw) as ShoppingListState;
  } catch {
    return createEmptyState();
  }
}

export function saveState(state: ShoppingListState): void {
  if (!storageAvailable()) return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}
