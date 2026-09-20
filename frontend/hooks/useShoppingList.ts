"use client";

import { useCallback, useSyncExternalStore } from "react";
import { shoppingListStore } from "@/lib/appServices";
import {
  addItem,
  addPreference,
  AddItemInput,
  PreferenceKind,
  removeItem,
  removePreference,
  setCategory,
  setQuantity,
  ShoppingListState,
  toggleFavorite,
} from "@/lib/shoppingList";

export function useShoppingList() {
  const state = useSyncExternalStore(
    shoppingListStore.subscribe,
    shoppingListStore.getSnapshot,
    shoppingListStore.getServerSnapshot
  );

  const update = useCallback(
    (fn: (s: ShoppingListState) => ShoppingListState) => shoppingListStore.update(fn),
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
