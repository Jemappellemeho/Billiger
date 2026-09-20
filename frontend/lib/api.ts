import type { StreakSummary } from "./streak";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Offer = {
  advertiser: string;
  price: number;
  old_price: number | null;
  reference_price: number | null;
};

export type NormalizedQuantity = {
  amount: number;
  unit: string;
};

export type ProductGroup = {
  brand: string | null;
  name: string | null;
  categories: string[];
  normalized_quantity: NormalizedQuantity | null;
  offers: Offer[];
  cheapest: Offer;
};

export type SearchResponse = {
  query: string;
  zip_code: string;
  results: ProductGroup[];
};

export type SearchLocation = { zipCode: string } | { lat: number; lon: number };

export class SearchError extends Error {}

export async function searchProducts(
  query: string,
  location: SearchLocation
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query });
  if ("zipCode" in location) {
    params.set("zip_code", location.zipCode);
  } else {
    params.set("lat", String(location.lat));
    params.set("lon", String(location.lon));
  }

  const response = await fetch(`${API_BASE_URL}/api/search/?${params.toString()}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}) as { detail?: string });
    throw new SearchError(body.detail ?? `Suche fehlgeschlagen (${response.status})`);
  }
  return response.json();
}

export type CartCompareItem = {
  name: string;
  brand?: string | null;
  quantity: number;
};

export type CartLine = {
  name: string;
  brand: string | null;
  quantity: number;
  advertiser: string;
  price: number;
  savings_vs_most_expensive: number;
  savings_vs_regular: number | null;
};

export type StoreTotal = {
  advertiser: string;
  covers_all_items: boolean;
  total: number | null;
  missing_items: string[];
};

export type SingleStoreResult = {
  advertiser: string;
  total: number;
  items: CartLine[];
} | null;

export type FullSplitResult = {
  total: number;
  assignment: CartLine[];
};

export type LadderRung = {
  stops: number;
  stores: string[];
  total: number;
  marginal_savings: number;
  assignment: CartLine[];
};

export type CartComparisonResponse = {
  zip_code: string;
  unavailable_items: string[];
  store_totals: StoreTotal[];
  single_store: SingleStoreResult;
  full_split: FullSplitResult;
  ladder: LadderRung[];
};

export class CartComparisonError extends Error {}

/** With a `token`, the comparison also counts toward the account's weekly streak. */
export async function compareCart(
  items: CartCompareItem[],
  location: SearchLocation,
  token?: string
): Promise<CartComparisonResponse> {
  const body: Record<string, unknown> = { items };
  if ("zipCode" in location) {
    body.zip_code = location.zipCode;
  } else {
    body.lat = location.lat;
    body.lon = location.lon;
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Token ${token}`;

  const response = await fetch(`${API_BASE_URL}/api/compare/`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const responseBody = await response.json().catch(() => ({}) as { detail?: string });
    throw new CartComparisonError(
      responseBody.detail ?? `Warenkorb-Vergleich fehlgeschlagen (${response.status})`
    );
  }
  return response.json();
}

export class StreakError extends Error {}

export async function fetchStreakSummary(token: string): Promise<StreakSummary> {
  const response = await fetch(`${API_BASE_URL}/api/streak/`, {
    headers: { Authorization: `Token ${token}` },
  });
  if (!response.ok) {
    throw new StreakError(`Streak konnte nicht geladen werden (${response.status})`);
  }
  return response.json();
}
