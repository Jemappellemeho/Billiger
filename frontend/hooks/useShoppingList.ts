"use client";

import { useCallback, useSyncExternalStore } from "react";
import {
  addExcludedIngredient,
  addExcludedStore,
  addItem,
  addPreferredBrand,
  AddItemInput,
  createEmptyState,
  removeExcludedIngredient,
  removeExcludedStore,
  removeItem,
  removePreferredBrand,
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
    addPreferredBrand: useCallback(
      (brand: string) => update((s) => addPreferredBrand(s, brand)),
      [update]
    ),
    removePreferredBrand: useCallback(
      (brand: string) => update((s) => removePreferredBrand(s, brand)),
      [update]
    ),
    addExcludedIngredient: useCallback(
      (ingredient: string) => update((s) => addExcludedIngredient(s, ingredient)),
      [update]
    ),
    removeExcludedIngredient: useCallback(
      (ingredient: string) => update((s) => removeExcludedIngredient(s, ingredient)),
      [update]
    ),
    addExcludedStore: useCallback(
      (store: string) => update((s) => addExcludedStore(s, store)),
      [update]
    ),
    removeExcludedStore: useCallback(
      (store: string) => update((s) => removeExcludedStore(s, store)),
      [update]
    ),
  };
}
