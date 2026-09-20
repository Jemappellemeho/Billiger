import { describe, expect, test, vi } from "vitest";
import { AssistantApi, AssistantError, ChatAnswer, ChatRequest } from "./assistantApi";
import { createAssistantChat, MAX_HISTORY_MESSAGES } from "./assistantChat";

const context = { token: "t1", location: { zipCode: "1010" } };

function answer(reply: string): ChatAnswer {
  return { reply, actions: [] };
}

function fakeApi(...replies: (string | Error)[]) {
  const requests: ChatRequest[] = [];
  const chat = vi.fn(async (request: ChatRequest) => {
    requests.push(structuredClone(request));
    const next = replies.shift() ?? "ok";
    if (next instanceof Error) throw next;
    return answer(next);
  });
  return { api: { chat } satisfies AssistantApi, requests };
}

function contents(chat: ReturnType<typeof createAssistantChat>) {
  return chat.getSnapshot().messages.map((m) => [m.role, m.content]);
}

describe("assistant chat", () => {
  test("a typed message shows up immediately and is followed by the assistant's reply", async () => {
    const { api } = fakeApi("Bei Lidl für 0,99 €.");
    const chat = createAssistantChat({ api });

    const sending = chat.send("Wo ist Milch am billigsten?", context);

    expect(contents(chat)).toEqual([["user", "Wo ist Milch am billigsten?"]]);
    expect(chat.getSnapshot().pending).toBe(true);

    await sending;

    expect(contents(chat)).toEqual([
      ["user", "Wo ist Milch am billigsten?"],
      ["assistant", "Bei Lidl für 0,99 €."],
    ]);
    expect(chat.getSnapshot().pending).toBe(false);
  });

  test("the request carries the token, location and the message as typed text", async () => {
    const { api, requests } = fakeApi("Hallo!");

    await createAssistantChat({ api }).send("Hallo", context);

    expect(requests).toEqual([
      { token: "t1", message: "Hallo", input: "text", history: [], location: { zipCode: "1010" } },
    ]);
  });

  test("a voice transcript takes the same path as typed text, shown as a transcribed bubble", async () => {
    const typed = fakeApi("Antwort");
    const spoken = fakeApi("Antwort");
    const typedChat = createAssistantChat({ api: typed.api });
    const spokenChat = createAssistantChat({ api: spoken.api });

    await typedChat.send("Was steht auf meiner Liste?", context);
    await spokenChat.send("Was steht auf meiner Liste?", { ...context, input: "voice" });

    expect(spoken.requests).toEqual([{ ...typed.requests[0], input: "voice" }]);
    expect(contents(spokenChat)).toEqual(contents(typedChat));
    expect(spokenChat.getSnapshot().messages[0].input).toBe("voice");
    expect(typedChat.getSnapshot().messages[0].input).toBe("text");
  });

  test("earlier messages are sent along as history", async () => {
    const { api, requests } = fakeApi("Bei Lidl.", "Bei Hofer.");
    const chat = createAssistantChat({ api });

    await chat.send("Milch?", context);
    await chat.send("Und Nutella?", context);

    expect(requests[1].history).toEqual([
      { role: "user", content: "Milch?" },
      { role: "assistant", content: "Bei Lidl." },
    ]);
  });

  test("a failed request shows an error bubble that is kept out of the history", async () => {
    const { api, requests } = fakeApi(new AssistantError("Der Assistent ist derzeit nicht erreichbar."), "Bei Hofer.");
    const chat = createAssistantChat({ api });

    await chat.send("Milch?", context);

    expect(contents(chat)).toEqual([
      ["user", "Milch?"],
      ["assistant", "Der Assistent ist derzeit nicht erreichbar."],
    ]);
    expect(chat.getSnapshot().messages[1].failed).toBe(true);
    expect(chat.getSnapshot().pending).toBe(false);

    await chat.send("Nutella?", context);

    expect(requests[1].history).toEqual([{ role: "user", content: "Milch?" }]);
  });

  test("an unexpected failure still ends in a readable error bubble", async () => {
    const { api } = fakeApi(new TypeError("Failed to fetch"));
    const chat = createAssistantChat({ api });

    await chat.send("Milch?", context);

    expect(chat.getSnapshot().messages[1]).toMatchObject({ role: "assistant", failed: true });
    expect(chat.getSnapshot().messages[1].content).toMatch(/nicht erreichbar/);
  });

  test("blank messages are ignored", async () => {
    const { api } = fakeApi();
    const chat = createAssistantChat({ api });

    await chat.send("   ", context);

    expect(api.chat).not.toHaveBeenCalled();
    expect(chat.getSnapshot().messages).toEqual([]);
  });

  test("a second message while one is being answered is ignored", async () => {
    const { api } = fakeApi("Erste Antwort");
    const chat = createAssistantChat({ api });

    const first = chat.send("Eins", context);
    await chat.send("Zwei", context);
    await first;

    expect(api.chat).toHaveBeenCalledTimes(1);
    expect(contents(chat)).toEqual([
      ["user", "Eins"],
      ["assistant", "Erste Antwort"],
    ]);
  });

  test("the history is capped and always starts with a user message", async () => {
    const { api, requests } = fakeApi(...Array.from({ length: 30 }, (_, i) => `Antwort ${i}`), "Letzte");
    const chat = createAssistantChat({ api });
    for (let i = 0; i < 30; i++) await chat.send(`Frage ${i}`, context);

    await chat.send("Frage 30", context);

    const history = requests.at(-1)!.history;
    expect(history.length).toBeLessThanOrEqual(MAX_HISTORY_MESSAGES);
    expect(history[0].role).toBe("user");
    expect(history.at(-1)).toEqual({ role: "assistant", content: "Antwort 29" });
  });

  test("resetting clears the conversation, and an answer that arrives afterwards is dropped", async () => {
    let release!: (value: ChatAnswer) => void;
    const api: AssistantApi = { chat: () => new Promise((resolve) => (release = resolve)) };
    const chat = createAssistantChat({ api });

    const sending = chat.send("Milch?", context);
    chat.reset();
    release(answer("Zu spät"));
    await sending;

    expect(chat.getSnapshot()).toEqual({ messages: [], pending: false });
  });

  test("subscribers are told about every change", async () => {
    const { api } = fakeApi("Hi");
    const chat = createAssistantChat({ api });
    const listener = vi.fn();
    chat.subscribe(listener);

    await chat.send("Hallo", context);

    expect(listener).toHaveBeenCalledTimes(2); // the user bubble (now pending), then the reply
  });
});
