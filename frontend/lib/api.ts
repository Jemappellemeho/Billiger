const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
