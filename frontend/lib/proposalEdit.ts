import type {
  PreferenceListKey,
  Proposal,
  ProposalChanges,
} from "./assistantApi";
import { MAX_QUANTITY } from "./shoppingList";

/**
 * The edit state behind "Ändern": a copy of what the proposal would result in, in a form the
 * user can adjust. It is sent back as `ProposalChanges` and answered with a fresh diff.
 */
export type ProposalDraft =
  | {
      kind: "shopping_list";
      rows: { id: string; name: string; brand: string | null; category: string | null; quantity: number; removed: boolean }[];
    }
  | {
      kind: "preferences";
      /** Comma-separated text for each list the proposal touches. */
      lists: Partial<Record<PreferenceListKey, string>>;
      /** Ids of the items that are favorites, if the proposal touches favorites. */
      favorites: string[] | null;
    }
  | { kind: "location"; zipCode: string };

export const PREFERENCE_LIST_KEYS: PreferenceListKey[] = [
  "preferred_brands",
  "excluded_ingredients",
  "excluded_stores",
];

export function splitList(text: string): string[] {
  return text
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function startEditing(proposal: Proposal): ProposalDraft {
  switch (proposal.kind) {
    case "shopping_list":
      return {
        kind: "shopping_list",
        rows: proposal.proposed.items.map(({ id, name, brand, category, quantity }) => ({
          id,
          name,
          brand,
          category,
          quantity,
          removed: false,
        })),
      };
    case "preferences": {
      const lists: Partial<Record<PreferenceListKey, string>> = {};
      for (const key of PREFERENCE_LIST_KEYS) {
        const entries = proposal.proposed[key];
        if (entries) lists[key] = entries.join(", ");
      }
      return { kind: "preferences", lists, favorites: proposal.proposed.favorite_items ?? null };
    }
    case "location":
      return { kind: "location", zipCode: proposal.proposed.zip_code };
  }
}

function clampQuantity(quantity: number) {
  if (!Number.isFinite(quantity)) return 1;
  return Math.min(MAX_QUANTITY, Math.max(1, Math.round(quantity)));
}

export function toChanges(draft: ProposalDraft): ProposalChanges {
  switch (draft.kind) {
    case "shopping_list":
      return {
        items: draft.rows
          .filter((row) => !row.removed)
          .map(({ name, brand, category, quantity }) => ({
            name,
            brand,
            category,
            quantity: clampQuantity(quantity),
          })),
      };
    case "preferences": {
      const changes: ProposalChanges = {};
      for (const key of PREFERENCE_LIST_KEYS) {
        const text = draft.lists[key];
        if (text !== undefined) changes[key] = splitList(text);
      }
      if (draft.favorites) changes.favorite_items = draft.favorites;
      return changes;
    }
    case "location":
      return { zip_code: draft.zipCode.trim() };
  }
}
