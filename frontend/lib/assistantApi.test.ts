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
  return { url, init, body: JSON.parse(init.body as string) };
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
    expect(answer).toEqual({ reply: "Bei Lidl.", actions: [] });
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
      new AssistantError("Der Assistent ist derzeit nicht erreichbar.")
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
});
