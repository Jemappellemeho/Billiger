import { afterEach, describe, expect, test, vi } from "vitest";
import { AssistantError } from "./assistantApi";
import { httpAssistantApi } from "./assistantApiHttp";

function respondWith(status: number, body?: unknown) {
  const fetchMock = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastRequest(fetchMock: ReturnType<typeof respondWith>) {
  const [url, init] = fetchMock.mock.calls.at(-1) as unknown as [string, RequestInit];
  return { url, init, body: init.body === undefined ? undefined : JSON.parse(init.body as string) };
}

const request = {
  token: "t1",
  message: "Wo ist Milch am billigsten?",
  input: "voice" as const,
  history: [{ role: "user" as const, content: "Hallo" }],
  location: { zipCode: "1010" },
};

afterEach(() => vi.unstubAllGlobals());

describe("assistant HTTP api", () => {
  test("posts the message with the token and a PLZ location", async () => {
    const fetchMock = respondWith(200, { reply: "Bei Lidl.", actions: [], user_message: {} });

    const answer = await httpAssistantApi.chat(request);

    const sent = lastRequest(fetchMock);
    expect(sent.url).toMatch(/\/api\/assistant\/chat\/$/);
    expect(sent.init.method).toBe("POST");
    expect(sent.init.headers).toMatchObject({ Authorization: "Token t1" });
    expect(sent.body).toEqual({
      message: "Wo ist Milch am billigsten?",
      input: "voice",
      history: [{ role: "user", content: "Hallo" }],
      zip_code: "1010",
    });
    expect(answer).toEqual({ reply: "Bei Lidl.", actions: [], proposals: [] });
  });

  test("sends GPS coordinates when there is no PLZ", async () => {
    const fetchMock = respondWith(200, { reply: "Ok", actions: [] });

    await httpAssistantApi.chat({ ...request, location: { lat: 48.2, lon: 16.37 } });

    expect(lastRequest(fetchMock).body).toMatchObject({ lat: 48.2, lon: 16.37 });
    expect(lastRequest(fetchMock).body).not.toHaveProperty("zip_code");
  });

  test("works without a known location", async () => {
    const fetchMock = respondWith(200, { reply: "Ok", actions: [] });

    await httpAssistantApi.chat({ ...request, location: null });

    const body = lastRequest(fetchMock).body;
    expect(body).not.toHaveProperty("zip_code");
    expect(body).not.toHaveProperty("lat");
  });

  test("surfaces the server's message on failure", async () => {
    respondWith(502, { detail: "Der Assistent ist derzeit nicht erreichbar." });

    await expect(httpAssistantApi.chat(request)).rejects.toThrow(
      new AssistantError("Der Assistent ist derzeit nicht erreichbar.", 502)
    );
  });

  test("explains a missing or expired sign-in", async () => {
    respondWith(401, { detail: "Invalid token." });

    await expect(httpAssistantApi.chat(request)).rejects.toThrow(/anmelden/);
  });

  test("explains rate limiting", async () => {
    respondWith(429, { detail: "Request was throttled." });

    await expect(httpAssistantApi.chat(request)).rejects.toThrow(/Moment/);
  });

  test("hands over the proposals the assistant made", async () => {
    const proposal = { id: 7, kind: "location", status: "pending", diff: {}, proposed: {} };
    respondWith(200, { reply: "Vorschlag", actions: [], proposals: [proposal] });

    const answer = await httpAssistantApi.chat(request);

    expect(answer.proposals).toEqual([proposal]);
  });
});

describe("assistant proposal decisions", () => {
  const proposal = { id: 7, kind: "shopping_list", status: "accepted", diff: {}, proposed: {} };

  test("accepting posts to the proposal and converts the returned list", async () => {
    const fetchMock = respondWith(200, {
      proposal,
      message: "✅ Einkaufsliste aktualisiert.",
      shopping_list: {
        items: [],
        preferences: { preferred_brands: ["Ferrero"], excluded_ingredients: [], excluded_stores: ["Penny"] },
      },
    });

    const outcome = await httpAssistantApi.decide("t1", 7, "accept");

    const sent = lastRequest(fetchMock);
    expect(sent.url).toMatch(/\/api\/assistant\/proposals\/7\/accept\/$/);
    expect(sent.init.method).toBe("POST");
    expect(sent.init.headers).toMatchObject({ Authorization: "Token t1" });
    expect(outcome).toEqual({
      proposal,
      message: "✅ Einkaufsliste aktualisiert.",
      shoppingList: {
        items: [],
        preferences: { preferredBrands: ["Ferrero"], excludedIngredients: [], excludedStores: ["Penny"] },
      },
      location: undefined,
    });
  });

  test("accepting a location change returns the new PLZ", async () => {
    respondWith(200, { proposal, message: "✅ Standort auf PLZ 8010 gesetzt.", location: { zip_code: "8010" } });

    const outcome = await httpAssistantApi.decide("t1", 7, "accept");

    expect(outcome.location).toEqual({ zipCode: "8010" });
    expect(outcome.shoppingList).toBeUndefined();
  });

  test("rejecting posts to the reject endpoint", async () => {
    const fetchMock = respondWith(200, {
      proposal: { ...proposal, status: "rejected" },
      message: "Verworfen — keine Änderung vorgenommen.",
    });

    const outcome = await httpAssistantApi.decide("t1", 7, "reject");

    expect(lastRequest(fetchMock).url).toMatch(/\/proposals\/7\/reject\/$/);
    expect(outcome.message).toBe("Verworfen — keine Änderung vorgenommen.");
  });

  test("editing puts the changed proposal and returns the fresh one", async () => {
    const fetchMock = respondWith(200, { proposal: { ...proposal, status: "pending" } });

    const revised = await httpAssistantApi.revise("t1", 7, { items: [] });

    const sent = lastRequest(fetchMock);
    expect(sent.url).toMatch(/\/proposals\/7\/$/);
    expect(sent.init.method).toBe("PUT");
    expect(sent.body).toEqual({ items: [] });
    expect(revised.status).toBe("pending");
  });

  test("loads the account's open proposals, including ones an external client made without a 'before'", async () => {
    const location = {
      id: 9,
      kind: "location",
      status: "pending",
      diff: { before: null, after: { zip_code: "8010" } },
      proposed: { zip_code: "8010" },
    };
    const fetchMock = respondWith(200, { proposals: [location, { ...proposal, status: "pending" }] });

    const open = await httpAssistantApi.openProposals("t1");

    const sent = lastRequest(fetchMock);
    expect(sent.url).toMatch(/\/api\/assistant\/proposals\/$/);
    expect(sent.init.method).toBe("GET");
    expect(sent.init.headers).toMatchObject({ Authorization: "Token t1" });
    expect(sent.init.body).toBeUndefined();
    expect(open).toEqual([location, { ...proposal, status: "pending" }]);
  });

  test("loading the open proposals explains a missing sign-in like the chat does", async () => {
    respondWith(401, { detail: "Invalid token." });

    await expect(httpAssistantApi.openProposals("t1")).rejects.toThrow(/anmelden/);
  });

  test("a conflict carries its status so the app can close the proposal", async () => {
    respondWith(409, { detail: "Über diesen Vorschlag wurde schon entschieden." });

    const error = await httpAssistantApi.decide("t1", 7, "accept").catch((e) => e);

    expect(error).toBeInstanceOf(AssistantError);
    expect(error.status).toBe(409);
    expect(error.message).toBe("Über diesen Vorschlag wurde schon entschieden.");
  });
});
