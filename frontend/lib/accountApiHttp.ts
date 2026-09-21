import { API_BASE_URL } from "./api";
import { AccountApi, AccountError, AuthResult, UnauthorizedError } from "./accountApi";
import { ShoppingListState } from "./shoppingList";

/** Wire format of the list (snake_case, like the rest of the API); see backend/accounts/serializers.py. */
export type WireList = {
  items: ShoppingListState["items"];
  preferences: {
    preferred_brands: string[];
    excluded_ingredients: string[];
    excluded_stores: string[];
  };
};

type AuthResponse = { token: string; email: string; shopping_list: WireList };

function toWire(state: ShoppingListState): WireList {
  return {
    items: state.items,
    preferences: {
      preferred_brands: state.preferences.preferredBrands,
      excluded_ingredients: state.preferences.excludedIngredients,
      excluded_stores: state.preferences.excludedStores,
    },
  };
}

export function fromWire(wire: WireList): ShoppingListState {
  return {
    items: wire.items,
    preferences: {
      preferredBrands: wire.preferences.preferred_brands,
      excludedIngredients: wire.preferences.excluded_ingredients,
      excludedStores: wire.preferences.excluded_stores,
    },
  };
}

/** DRF answers `{detail}` or `{field: [messages]}`; flatten either into one sentence. */
function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    const messages = Object.values(record).flatMap((value) =>
      Array.isArray(value) ? value.filter((entry) => typeof entry === "string") : []
    );
    if (messages.length > 0) return messages.join(" ");
  }
  return `Anfrage fehlgeschlagen (${status})`;
}

async function request<T>(
  path: string,
  { method = "GET", token, body }: { method?: string; token?: string; body?: unknown } = {}
): Promise<T> {
  const headers = new Headers();
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Token ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new AccountError("Der Server ist derzeit nicht erreichbar.");
  }

  const payload = await response.json().catch(() => undefined);
  if (!response.ok) {
    const message = errorMessage(payload, response.status);
    throw response.status === 401 ? new UnauthorizedError(message) : new AccountError(message);
  }
  return payload as T;
}

function toAuthResult(response: AuthResponse): AuthResult {
  return {
    session: { token: response.token, email: response.email },
    list: fromWire(response.shopping_list),
  };
}

async function authenticate(path: string, body: object, guestList: ShoppingListState) {
  const response = await request<AuthResponse>(path, {
    method: "POST",
    body: { ...body, guest_list: toWire(guestList) },
  });
  return toAuthResult(response);
}

export const httpAccountApi: AccountApi = {
  register: (email, password, guestList) =>
    authenticate("/api/auth/register/", { email, password }, guestList),
  login: (email, password, guestList) =>
    authenticate("/api/auth/login/", { email, password }, guestList),
  google: (idToken, guestList) =>
    authenticate("/api/auth/google/", { id_token: idToken }, guestList),
  async logout(token) {
    await request<void>("/api/auth/logout/", { method: "POST", token });
  },
  async fetchList(token) {
    return fromWire(await request<WireList>("/api/shopping-list/", { token }));
  },
  async saveList(token, state) {
    await request<WireList>("/api/shopping-list/", { method: "PUT", token, body: toWire(state) });
  },
};
