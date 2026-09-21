import { describe, expect, test } from "vitest";
import type { LocationProposal, PreferencesProposal, ShoppingListProposal } from "./assistantApi";
import { splitList, startEditing, toChanges } from "./proposalEdit";

const row = (name: string, quantity: number, extra = {}) => ({
  id: name.toLowerCase(),
  name,
  brand: null,
  category: null,
  favorite: false,
  quantity,
  ...extra,
});

const listProposal: ShoppingListProposal = {
  id: 1,
  kind: "shopping_list",
  status: "pending",
  diff: { added: [row("Butter", 2)], removed: [], changed: [], unchanged: [row("Milch", 1)] },
  proposed: { items: [row("Milch", 1, { category: "Molkerei" }), row("Butter", 2)] },
};

describe("editing a proposal", () => {
  test("a list proposal starts as the proposed list and goes back as the edited full list", () => {
    const draft = startEditing(listProposal);
    if (draft.kind !== "shopping_list") throw new Error("wrong draft");

    draft.rows[0].quantity = 3;
    draft.rows[1].removed = true;

    expect(toChanges(draft)).toEqual({
      items: [{ name: "Milch", brand: null, category: "Molkerei", quantity: 3 }],
    });
  });

  test("quantities are kept within what the list allows", () => {
    const draft = startEditing(listProposal);
    if (draft.kind !== "shopping_list") throw new Error("wrong draft");

    draft.rows[0].quantity = 0;
    draft.rows[1].quantity = 5000;
    expect(toChanges(draft)).toMatchObject({ items: [{ quantity: 1 }, { quantity: 999 }] });

    draft.rows[0].quantity = Number.NaN;
    expect(toChanges(draft)).toMatchObject({ items: [{ quantity: 1 }, { quantity: 999 }] });
  });

  test("a preference proposal is edited as comma-separated text, only for the parts it touches", () => {
    const proposal: PreferencesProposal = {
      id: 2,
      kind: "preferences",
      status: "pending",
      diff: {},
      proposed: { preferred_brands: ["Ja! Natürlich", "Ferrero"], favorite_items: ["milch"] },
    };

    const draft = startEditing(proposal);
    expect(draft).toEqual({
      kind: "preferences",
      lists: { preferred_brands: "Ja! Natürlich, Ferrero" },
      favorites: ["milch"],
    });
    if (draft.kind !== "preferences") throw new Error("wrong draft");

    draft.lists.preferred_brands = "Ferrero,  Milka ,";
    draft.favorites = [];
    expect(toChanges(draft)).toEqual({ preferred_brands: ["Ferrero", "Milka"], favorite_items: [] });
  });

  test("favorites are left out of the edit when the proposal doesn't touch them", () => {
    const proposal: PreferencesProposal = {
      id: 3,
      kind: "preferences",
      status: "pending",
      diff: {},
      proposed: { excluded_stores: ["Penny"] },
    };

    expect(toChanges(startEditing(proposal))).toEqual({ excluded_stores: ["Penny"] });
  });

  test("a location proposal is edited as the PLZ", () => {
    const proposal: LocationProposal = {
      id: 4,
      kind: "location",
      status: "pending",
      diff: { before: null, after: { zip_code: "8010" } },
      proposed: { zip_code: "8010" },
    };

    const draft = startEditing(proposal);
    if (draft.kind !== "location") throw new Error("wrong draft");
    draft.zipCode = " 5020 ";

    expect(toChanges(draft)).toEqual({ zip_code: "5020" });
  });

  test("splitList drops blanks", () => {
    expect(splitList(" a, ,b ,, ")).toEqual(["a", "b"]);
    expect(splitList("")).toEqual([]);
  });
});
