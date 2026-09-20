export type ShoppingListItem = {
  id: string;
  name: string;
  brand: string | null;
  category: string | null;
  favorite: boolean;
  quantity: number;
};

export type Preferences = {
  preferredBrands: string[];
  excludedIngredients: string[];
  excludedStores: string[];
};

export type ShoppingListState = {
  items: ShoppingListItem[];
  preferences: Preferences;
};

export type AddItemInput = {
  name: string;
  brand?: string | null;
  category?: string | null;
};

/**
 * Limits the account storage accepts (mirrors backend/accounts/serializers.py).
 * Guest state is kept within them so signing in can always migrate it.
 */
export const MAX_QUANTITY = 999;
export const MAX_NAME_LENGTH = 200;
export const MAX_BRAND_LENGTH = 100;
export const MAX_CATEGORY_LENGTH = 100;
export const MAX_ITEMS = 500;
export const MAX_PREFERENCE_ENTRIES = 100;
export const MAX_PREFERENCE_LENGTH = 100;

export function createEmptyState(): ShoppingListState {
  return {
    items: [],
    preferences: { preferredBrands: [], excludedIngredients: [], excludedStores: [] },
  };
}

/**
 * Identity is derived from brand+name rather than a generated id, so adding
 * the same product twice (by name, or via search) merges into one row with
 * an incremented quantity instead of creating a duplicate.
 */
function itemId(name: string, brand: string | null | undefined) {
  return `${brand?.trim().toLowerCase() ?? ""}|${name.trim().toLowerCase()}`.replace(/^\|/, "");
}

export function addItem(state: ShoppingListState, input: AddItemInput): ShoppingListState {
  const name = input.name.slice(0, MAX_NAME_LENGTH);
  const brand = input.brand?.slice(0, MAX_BRAND_LENGTH) ?? null;
  const id = itemId(name, brand);
  const existing = state.items.find((item) => item.id === id);

  if (existing) {
    return {
      ...state,
      items: state.items.map((item) =>
        item.id === id ? { ...item, quantity: item.quantity + 1 } : item
      ),
    };
  }

  const newItem: ShoppingListItem = {
    id,
    name,
    brand,
    category: input.category?.slice(0, MAX_CATEGORY_LENGTH) ?? null,
    favorite: false,
    quantity: 1,
  };
  if (state.items.length >= MAX_ITEMS) return state;
  return { ...state, items: [...state.items, newItem] };
}

export function removeItem(state: ShoppingListState, id: string): ShoppingListState {
  return { ...state, items: state.items.filter((item) => item.id !== id) };
}

export function setQuantity(
  state: ShoppingListState,
  id: string,
  quantity: number
): ShoppingListState {
  const clamped = Math.min(MAX_QUANTITY, Math.max(1, Math.round(quantity)));
  return {
    ...state,
    items: state.items.map((item) => (item.id === id ? { ...item, quantity: clamped } : item)),
  };
}

export function toggleFavorite(state: ShoppingListState, id: string): ShoppingListState {
  return {
    ...state,
    items: state.items.map((item) =>
      item.id === id ? { ...item, favorite: !item.favorite } : item
    ),
  };
}

export function setCategory(
  state: ShoppingListState,
  id: string,
  category: string | null
): ShoppingListState {
  return {
    ...state,
    items: state.items.map((item) =>
      item.id === id ? { ...item, category: category?.slice(0, MAX_CATEGORY_LENGTH) ?? null } : item
    ),
  };
}

export type PreferenceKind = keyof Preferences;

export function addPreference(
  state: ShoppingListState,
  kind: PreferenceKind,
  value: string
): ShoppingListState {
  const list = state.preferences[kind];
  const entry = value.slice(0, MAX_PREFERENCE_LENGTH);
  if (list.includes(entry) || list.length >= MAX_PREFERENCE_ENTRIES) return state;
  return { ...state, preferences: { ...state.preferences, [kind]: [...list, entry] } };
}

export function removePreference(
  state: ShoppingListState,
  kind: PreferenceKind,
  value: string
): ShoppingListState {
  return {
    ...state,
    preferences: {
      ...state.preferences,
      [kind]: state.preferences[kind].filter((entry) => entry !== value),
    },
  };
}
