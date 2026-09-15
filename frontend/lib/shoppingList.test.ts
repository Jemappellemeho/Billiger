import { describe, expect, test } from "vitest";
import {
  addItem,
  addPreference,
  createEmptyState,
  removeItem,
  removePreference,
  setCategory,
  setQuantity,
  toggleFavorite,
} from "./shoppingList";

describe("addItem", () => {
  test("adds a new item by name only, defaulting quantity to 1", () => {
    const state = addItem(createEmptyState(), { name: "Milch" });
    expect(state.items).toEqual([
      {
        id: "milch",
        name: "Milch",
        brand: null,
        category: null,
        favorite: false,
        quantity: 1,
      },
    ]);
  });

  test("adds an item found via search, carrying brand and category", () => {
    const state = addItem(createEmptyState(), {
      name: "Nutella",
      brand: "Ferrero",
      category: "Aufstriche",
    });
    expect(state.items).toEqual([
      {
        id: "ferrero|nutella",
        name: "Nutella",
        brand: "Ferrero",
        category: "Aufstriche",
        favorite: false,
        quantity: 1,
      },
    ]);
  });

  test("adding the same product again increments its quantity instead of duplicating", () => {
    let state = addItem(createEmptyState(), { name: "Milch", brand: "NÖM" });
    state = addItem(state, { name: "Milch", brand: "NÖM" });

    expect(state.items).toHaveLength(1);
    expect(state.items[0].quantity).toBe(2);
  });

  test("treats name/brand matching as case-insensitive", () => {
    let state = addItem(createEmptyState(), { name: "Milch" });
    state = addItem(state, { name: "milch" });

    expect(state.items).toHaveLength(1);
    expect(state.items[0].quantity).toBe(2);
  });
});

describe("removeItem", () => {
  test("removes the matching item and leaves others untouched", () => {
    let state = addItem(createEmptyState(), { name: "Milch" });
    state = addItem(state, { name: "Brot" });

    state = removeItem(state, "milch");

    expect(state.items).toEqual([
      expect.objectContaining({ id: "brot", name: "Brot" }),
    ]);
  });

  test("is a no-op when the id is not on the list", () => {
    const state = addItem(createEmptyState(), { name: "Milch" });
    expect(removeItem(state, "does-not-exist")).toEqual(state);
  });
});

describe("setQuantity", () => {
  test("updates the quantity of the matching item", () => {
    let state = addItem(createEmptyState(), { name: "Milch" });
    state = setQuantity(state, "milch", 5);
    expect(state.items[0].quantity).toBe(5);
  });

  test("clamps quantity to a minimum of 1", () => {
    let state = addItem(createEmptyState(), { name: "Milch" });
    state = setQuantity(state, "milch", 0);
    expect(state.items[0].quantity).toBe(1);
  });
});

describe("toggleFavorite", () => {
  test("flips favorite from false to true and back", () => {
    let state = addItem(createEmptyState(), { name: "Milch" });
    state = toggleFavorite(state, "milch");
    expect(state.items[0].favorite).toBe(true);

    state = toggleFavorite(state, "milch");
    expect(state.items[0].favorite).toBe(false);
  });
});

describe("setCategory", () => {
  test("assigns a category to an existing item", () => {
    let state = addItem(createEmptyState(), { name: "Milch" });
    state = setCategory(state, "milch", "Milchprodukte");
    expect(state.items[0].category).toBe("Milchprodukte");
  });

  test("clears a category by passing null", () => {
    let state = addItem(createEmptyState(), { name: "Milch", category: "Milchprodukte" });
    state = setCategory(state, "milch", null);
    expect(state.items[0].category).toBeNull();
  });
});

describe("preferences", () => {
  test("adds and removes a preferred brand without duplicates", () => {
    let state = addPreference(createEmptyState(), "preferredBrands", "NÖM");
    state = addPreference(state, "preferredBrands", "NÖM");
    expect(state.preferences.preferredBrands).toEqual(["NÖM"]);

    state = removePreference(state, "preferredBrands", "NÖM");
    expect(state.preferences.preferredBrands).toEqual([]);
  });

  test("adds and removes an excluded ingredient without duplicates", () => {
    let state = addPreference(createEmptyState(), "excludedIngredients", "Laktose");
    state = addPreference(state, "excludedIngredients", "Laktose");
    expect(state.preferences.excludedIngredients).toEqual(["Laktose"]);

    state = removePreference(state, "excludedIngredients", "Laktose");
    expect(state.preferences.excludedIngredients).toEqual([]);
  });

  test("adds and removes an excluded store without duplicates", () => {
    let state = addPreference(createEmptyState(), "excludedStores", "Hofer");
    state = addPreference(state, "excludedStores", "Hofer");
    expect(state.preferences.excludedStores).toEqual(["Hofer"]);

    state = removePreference(state, "excludedStores", "Hofer");
    expect(state.preferences.excludedStores).toEqual([]);
  });

  test("preference kinds are independent of one another", () => {
    let state = addPreference(createEmptyState(), "preferredBrands", "NÖM");
    state = addPreference(state, "excludedStores", "NÖM");
    expect(state.preferences.preferredBrands).toEqual(["NÖM"]);
    expect(state.preferences.excludedStores).toEqual(["NÖM"]);
  });
});
