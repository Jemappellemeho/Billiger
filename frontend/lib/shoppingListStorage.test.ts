import { beforeEach, describe, expect, test } from "vitest";
import { addItem, createEmptyState } from "./shoppingList";
import { loadState, saveState } from "./shoppingListStorage";

describe("shopping list persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test("a saved list is readable again as the same state (guest mode, no server round trip)", () => {
    const state = addItem(createEmptyState(), { name: "Milch", brand: "NÖM" });

    saveState(state);

    expect(loadState()).toEqual(state);
  });

  test("loading with nothing saved yet returns an empty list", () => {
    expect(loadState()).toEqual(createEmptyState());
  });

  test("loading corrupted storage falls back to an empty list instead of throwing", () => {
    localStorage.setItem("billiger:shopping-list", "{not valid json");
    expect(loadState()).toEqual(createEmptyState());
  });
});
