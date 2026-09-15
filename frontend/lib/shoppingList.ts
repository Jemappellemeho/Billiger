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
  const brand = input.brand ?? null;
  const id = itemId(input.name, brand);
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
    name: input.name,
    brand,
    category: input.category ?? null,
    favorite: false,
    quantity: 1,
  };
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
  const clamped = Math.max(1, Math.round(quantity));
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
    items: state.items.map((item) => (item.id === id ? { ...item, category } : item)),
  };
}

function addPreference(list: string[], value: string): string[] {
  return list.includes(value) ? list : [...list, value];
}

function removePreference(list: string[], value: string): string[] {
  return list.filter((entry) => entry !== value);
}

export function addPreferredBrand(state: ShoppingListState, brand: string): ShoppingListState {
  return {
    ...state,
    preferences: {
      ...state.preferences,
      preferredBrands: addPreference(state.preferences.preferredBrands, brand),
    },
  };
}

export function removePreferredBrand(state: ShoppingListState, brand: string): ShoppingListState {
  return {
    ...state,
    preferences: {
      ...state.preferences,
      preferredBrands: removePreference(state.preferences.preferredBrands, brand),
    },
  };
}

export function addExcludedIngredient(
  state: ShoppingListState,
  ingredient: string
): ShoppingListState {
  return {
    ...state,
    preferences: {
      ...state.preferences,
      excludedIngredients: addPreference(state.preferences.excludedIngredients, ingredient),
    },
  };
}

export function removeExcludedIngredient(
  state: ShoppingListState,
  ingredient: string
): ShoppingListState {
  return {
    ...state,
    preferences: {
      ...state.preferences,
      excludedIngredients: removePreference(state.preferences.excludedIngredients, ingredient),
    },
  };
}

export function addExcludedStore(state: ShoppingListState, store: string): ShoppingListState {
  return {
    ...state,
    preferences: {
      ...state.preferences,
      excludedStores: addPreference(state.preferences.excludedStores, store),
    },
  };
}

export function removeExcludedStore(state: ShoppingListState, store: string): ShoppingListState {
  return {
    ...state,
    preferences: {
      ...state.preferences,
      excludedStores: removePreference(state.preferences.excludedStores, store),
    },
  };
}
