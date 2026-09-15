"use client";

import { useCallback, useSyncExternalStore } from "react";
import {
  addItem,
  addPreference,
  AddItemInput,
  createEmptyState,
  PreferenceKind,
  removeItem,
  removePreference,
  setCategory,
  setQuantity,
  ShoppingListState,
  toggleFavorite,
} from "@/lib/shoppingList";
import { loadState, saveState } from "@/lib/shoppingListStorage";

type Listener = () => void;

/**
 * A module-level store (not per-component state) so useSyncExternalStore can
 * give every caller the same guest-mode list and match the SSR snapshot
 * (empty, since localStorage isn't reachable on the server) without the
 * mount-time setState-in-effect pattern that causes cascading renders.
 */
const listeners = new Set<Listener>();
let cachedState: ShoppingListState | null = null;
const serverSnapshot = createEmptyState();

function getSnapshot(): ShoppingListState {
  if (cachedState === null) {
    cachedState = loadState();
  }
  return cachedState;
}

function getServerSnapshot(): ShoppingListState {
  return serverSnapshot;
}

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function commit(next: ShoppingListState) {
  cachedState = next;
  saveState(next);
  listeners.forEach((listener) => listener());
}

export function useShoppingList() {
  const state = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const update = useCallback(
    (fn: (s: ShoppingListState) => ShoppingListState) => commit(fn(getSnapshot())),
    []
  );

  return {
    items: state.items,
    preferences: state.preferences,
    addItem: useCallback((input: AddItemInput) => update((s) => addItem(s, input)), [update]),
    removeItem: useCallback((id: string) => update((s) => removeItem(s, id)), [update]),
    setQuantity: useCallback(
      (id: string, quantity: number) => update((s) => setQuantity(s, id, quantity)),
      [update]
    ),
    toggleFavorite: useCallback((id: string) => update((s) => toggleFavorite(s, id)), [update]),
    setCategory: useCallback(
      (id: string, category: string | null) => update((s) => setCategory(s, id, category)),
      [update]
    ),
    addPreference: useCallback(
      (kind: PreferenceKind, value: string) => update((s) => addPreference(s, kind, value)),
      [update]
    ),
    removePreference: useCallback(
      (kind: PreferenceKind, value: string) => update((s) => removePreference(s, kind, value)),
      [update]
    ),
  };
}
