import { afterEach, describe, expect, test, vi } from "vitest";
import { AccountError, UnauthorizedError } from "./accountApi";
import { httpAccountApi } from "./accountApiHttp";
import { addItem, addPreference, createEmptyState } from "./shoppingList";

const guest = addPreference(
  addItem(createEmptyState(), { name: "Milch", brand: "NÖM" }),
  "excludedStores",
  "Lidl"
);

const wireList = {
  items: [
    { id: "nöm|milch", name: "Milch", brand: "NÖM", category: null, favorite: false, quantity: 1 },
  ],
  preferences: { preferred_brands: [], excluded_ingredients: [], excluded_stores: ["Lidl"] },
};

function respondWith(status: number, body?: unknown) {
  const fetchMock = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastRequest(fetchMock: ReturnType<typeof respondWith>) {
  const [url, init] = fetchMock.mock.calls.at(-1) as unknown as [string, RequestInit];
  return { url, init, body: init.body ? JSON.parse(init.body as string) : undefined };
}

afterEach(() => vi.unstubAllGlobals());

describe("account HTTP api", () => {
  test("login sends the guest list in wire format and maps the answer back", async () => {
    const fetchMock = respondWith(200, { token: "t1", email: "anna@example.com", shopping_list: wireList });

    const result = await httpAccountApi.login("anna@example.com", "pw", guest);

    const request = lastRequest(fetchMock);
    expect(request.url).toMatch(/\/api\/auth\/login\/$/);
    expect(request.init.method).toBe("POST");
    expect(request.body).toEqual({ email: "anna@example.com", password: "pw", guest_list: wireList });
    expect(result).toEqual({ session: { token: "t1", email: "anna@example.com" }, list: guest });
  });

  test("register and Google sign-in post to their own endpoints", async () => {
    const fetchMock = respondWith(201, { token: "t1", email: "a@b.at", shopping_list: wireList });

    await httpAccountApi.register("a@b.at", "pw", guest);
    expect(lastRequest(fetchMock).url).toMatch(/\/api\/auth\/register\/$/);

    await httpAccountApi.google("jwt", guest);
    const google = lastRequest(fetchMock);
    expect(google.url).toMatch(/\/api\/auth\/google\/$/);
    expect(google.body).toEqual({ id_token: "jwt", guest_list: wireList });
  });

  test("a rejected request surfaces the server's message", async () => {
    respondWith(400, { detail: "E-Mail oder Passwort ist falsch." });
    await expect(httpAccountApi.login("a@b.at", "x", guest)).rejects.toThrow(
      "E-Mail oder Passwort ist falsch."
    );

    respondWith(400, { email: ["Diese E-Mail ist bereits registriert."], password: ["Zu kurz."] });
    await expect(httpAccountApi.register("a@b.at", "x", guest)).rejects.toThrow(
      "Diese E-Mail ist bereits registriert. Zu kurz."
    );
  });

  test("fetching the list authenticates with the token and maps the wire format", async () => {
    const fetchMock = respondWith(200, wireList);

    const list = await httpAccountApi.fetchList("t1");

    const request = lastRequest(fetchMock);
    expect(request.url).toMatch(/\/api\/shopping-list\/$/);
    expect(new Headers(request.init.headers).get("Authorization")).toBe("Token t1");
    expect(list).toEqual(guest);
  });

  test("a rejected token is reported as unauthorized", async () => {
    respondWith(401, { detail: "Ungültiges Token." });

    await expect(httpAccountApi.fetchList("stale")).rejects.toBeInstanceOf(UnauthorizedError);
  });

  test("saving the list replaces the account's list in wire format", async () => {
    const fetchMock = respondWith(200, wireList);

    await httpAccountApi.saveList("t1", guest);

    const request = lastRequest(fetchMock);
    expect(request.init.method).toBe("PUT");
    expect(request.body).toEqual(wireList);
  });

  test("signing out revokes the token", async () => {
    const fetchMock = respondWith(204);

    await httpAccountApi.logout("t1");

    const request = lastRequest(fetchMock);
    expect(request.url).toMatch(/\/api\/auth\/logout\/$/);
    expect(new Headers(request.init.headers).get("Authorization")).toBe("Token t1");
  });

  test("an unreachable server is an account error, not a crash", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));

    await expect(httpAccountApi.fetchList("t1")).rejects.toBeInstanceOf(AccountError);
  });
});
