import { describe, expect, test, vi } from "vitest";
import {
  AssistantApi,
  AssistantError,
  ChatAnswer,
  ChatRequest,
  Proposal,
  ProposalOutcome,
} from "./assistantApi";
import { createAssistantChat, MAX_HISTORY_MESSAGES } from "./assistantChat";

const context = { token: "t1", location: { zipCode: "1010" } };

function answer(reply: string, proposals: Proposal[] = []): ChatAnswer {
  return { reply, actions: [], proposals };
}

/** An api whose proposal endpoints must not be reached, unless a test provides them. */
function chatOnly(chat: AssistantApi["chat"], rest: Partial<AssistantApi> = {}): AssistantApi {
  return {
    chat,
    decide: vi.fn(async () => {
      throw new Error("unexpected decide");
    }),
    revise: vi.fn(async () => {
      throw new Error("unexpected revise");
    }),
    ...rest,
  };
}

function fakeApi(...replies: (string | Error)[]) {
  const requests: ChatRequest[] = [];
  const chat = vi.fn(async (request: ChatRequest) => {
    requests.push(structuredClone(request));
    const next = replies.shift() ?? "ok";
    if (next instanceof Error) throw next;
    return answer(next);
  });
  return { api: chatOnly(chat), requests };
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
    const api = chatOnly(() => new Promise((resolve) => (release = resolve)));
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

const butter = { id: "butter", name: "Butter", brand: null, category: null, favorite: false, quantity: 2 };

const listProposal: Proposal = {
  id: 7,
  kind: "shopping_list",
  status: "pending",
  diff: { added: [butter], removed: [], changed: [], unchanged: [] },
  proposed: { items: [butter] },
};

const locationProposal: Proposal = {
  id: 8,
  kind: "location",
  status: "pending",
  diff: { before: { zip_code: "1010" }, after: { zip_code: "8010" } },
  proposed: { zip_code: "8010" },
};

const newList = {
  items: [butter],
  preferences: { preferredBrands: [], excludedIngredients: [], excludedStores: [] },
};

function outcome(proposal: Proposal, status: Proposal["status"], message: string, rest = {}): ProposalOutcome {
  return { proposal: { ...proposal, status }, message, ...rest };
}

/** A chat in which the assistant has just made `proposals`, with the decision endpoints faked. */
async function chatWithProposals(proposals: Proposal[], api: Partial<AssistantApi> = {}) {
  const applyList = vi.fn();
  const chat = createAssistantChat({
    api: chatOnly(async () => answer("Mein Vorschlag.", proposals), api),
    applyList,
  });
  await chat.send("Ändere etwas", context);
  return { chat, applyList };
}

function proposalOf(chat: ReturnType<typeof createAssistantChat>, id: number) {
  return chat.getSnapshot().messages.flatMap((m) => m.proposals).find((p) => p.proposal.id === id)!;
}

describe("assistant proposals", () => {
  test("a proposal arrives with the assistant's message, still open and unapplied", async () => {
    const { chat, applyList } = await chatWithProposals([listProposal]);

    const [, reply] = chat.getSnapshot().messages;
    expect(reply.content).toBe("Mein Vorschlag.");
    expect(reply.proposals).toEqual([{ proposal: listProposal, busy: false, error: null }]);
    expect(applyList).not.toHaveBeenCalled();
  });

  test("accepting applies the new list and ends in a confirmation message", async () => {
    const decide = vi.fn(async () =>
      outcome(listProposal, "accepted", "✅ Einkaufsliste aktualisiert.", { shoppingList: newList })
    );
    const { chat, applyList } = await chatWithProposals([listProposal], { decide });

    await chat.decide(7, "accept", { token: "t1" });

    expect(decide).toHaveBeenCalledWith("t1", 7, "accept");
    expect(applyList).toHaveBeenCalledWith(newList);
    expect(proposalOf(chat, 7)).toEqual({
      proposal: { ...listProposal, status: "accepted" },
      busy: false,
      error: null,
    });
    expect(chat.getSnapshot().messages.at(-1)).toMatchObject({
      role: "assistant",
      content: "✅ Einkaufsliste aktualisiert.",
      failed: false,
    });
  });

  test("the confirmation becomes part of the history the assistant sees next", async () => {
    const decide = vi.fn(async () => outcome(listProposal, "accepted", "✅ Einkaufsliste aktualisiert."));
    const requests: ChatRequest[] = [];
    const chatFn = vi.fn(async (request: ChatRequest) => {
      requests.push(structuredClone(request));
      return answer("Mein Vorschlag.", requests.length === 1 ? [listProposal] : []);
    });
    const chat = createAssistantChat({ api: chatOnly(chatFn, { decide }) });
    await chat.send("Butter dazu", context);
    await chat.decide(7, "accept", { token: "t1" });

    await chat.send("Danke", context);

    expect(requests[1].history.at(-1)).toEqual({ role: "assistant", content: "✅ Einkaufsliste aktualisiert." });
  });

  test("accepting a location change hands the new PLZ to the app", async () => {
    const decide = vi.fn(async () =>
      outcome(locationProposal, "accepted", "✅ Standort auf PLZ 8010 gesetzt.", { location: { zipCode: "8010" } })
    );
    const { chat, applyList } = await chatWithProposals([locationProposal], { decide });
    const onLocationChange = vi.fn();

    await chat.decide(8, "accept", { token: "t1", onLocationChange });

    expect(onLocationChange).toHaveBeenCalledWith("8010");
    expect(applyList).not.toHaveBeenCalled();
    expect(chat.getSnapshot().messages.at(-1)!.content).toBe("✅ Standort auf PLZ 8010 gesetzt.");
  });

  test("rejecting applies nothing and says so", async () => {
    const decide = vi.fn(async () => outcome(locationProposal, "rejected", "Verworfen — keine Änderung vorgenommen."));
    const { chat, applyList } = await chatWithProposals([locationProposal], { decide });
    const onLocationChange = vi.fn();

    await chat.decide(8, "reject", { token: "t1", onLocationChange });

    expect(decide).toHaveBeenCalledWith("t1", 8, "reject");
    expect(applyList).not.toHaveBeenCalled();
    expect(onLocationChange).not.toHaveBeenCalled();
    expect(proposalOf(chat, 8).proposal.status).toBe("rejected");
    expect(chat.getSnapshot().messages.at(-1)!.content).toBe("Verworfen — keine Änderung vorgenommen.");
  });

  test("a decided proposal cannot be decided again", async () => {
    const decide = vi.fn(async () => outcome(listProposal, "rejected", "Verworfen — keine Änderung vorgenommen."));
    const { chat } = await chatWithProposals([listProposal], { decide });

    await chat.decide(7, "reject", { token: "t1" });
    await chat.decide(7, "accept", { token: "t1" });

    expect(decide).toHaveBeenCalledTimes(1);
  });

  test("a failed decision keeps the proposal open with the reason, and can be retried", async () => {
    const decide = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(outcome(listProposal, "accepted", "✅ Einkaufsliste aktualisiert."));
    const { chat } = await chatWithProposals([listProposal], { decide });

    await chat.decide(7, "accept", { token: "t1" });

    expect(proposalOf(chat, 7)).toMatchObject({ busy: false, proposal: { status: "pending" } });
    expect(proposalOf(chat, 7).error).toMatch(/nicht erreichbar/);
    expect(chat.getSnapshot().messages).toHaveLength(2); // no confirmation for a decision that didn't happen

    await chat.decide(7, "accept", { token: "t1" });

    expect(proposalOf(chat, 7)).toMatchObject({ error: null, proposal: { status: "accepted" } });
  });

  test("a proposal the server calls outdated is closed with the server's explanation", async () => {
    const decide = vi.fn(async () => {
      throw new AssistantError("Die Daten haben sich seit dem Vorschlag geändert.", 409);
    });
    const { chat, applyList } = await chatWithProposals([listProposal], { decide });

    await chat.decide(7, "accept", { token: "t1" });

    expect(proposalOf(chat, 7)).toMatchObject({
      proposal: { status: "stale" },
      error: "Die Daten haben sich seit dem Vorschlag geändert.",
    });
    expect(applyList).not.toHaveBeenCalled();
  });

  test("editing shows the fresh diff and keeps the proposal open", async () => {
    const edited: Proposal = { ...listProposal, diff: { ...listProposal.diff, added: [] } } as Proposal;
    const revise = vi.fn(async () => edited);
    const { chat } = await chatWithProposals([listProposal], { revise });

    const ok = await chat.revise(7, { items: [] }, { token: "t1" });

    expect(ok).toBe(true);
    expect(revise).toHaveBeenCalledWith("t1", 7, { items: [] });
    expect(proposalOf(chat, 7)).toEqual({ proposal: edited, busy: false, error: null });
    expect(chat.getSnapshot().messages).toHaveLength(2);
  });

  test("an edit the server refuses keeps the old diff and shows why", async () => {
    const revise = vi.fn(async () => {
      throw new AssistantError("Der Vorschlag entspricht dem aktuellen Stand — es gibt nichts zu ändern.", 400);
    });
    const { chat } = await chatWithProposals([listProposal], { revise });

    const ok = await chat.revise(7, { items: [] }, { token: "t1" });

    expect(ok).toBe(false);
    expect(proposalOf(chat, 7)).toMatchObject({ proposal: listProposal, busy: false });
    expect(proposalOf(chat, 7).error).toMatch(/nichts zu ändern/);
  });

  test("a decision that arrives after a reset is dropped and applies nothing", async () => {
    let release!: (value: ProposalOutcome) => void;
    const decide = vi.fn(() => new Promise<ProposalOutcome>((resolve) => (release = resolve)));
    const { chat, applyList } = await chatWithProposals([listProposal], { decide });

    const deciding = chat.decide(7, "accept", { token: "t1" });
    chat.reset();
    release(outcome(listProposal, "accepted", "✅ Einkaufsliste aktualisiert.", { shoppingList: newList }));
    await deciding;

    expect(applyList).not.toHaveBeenCalled();
    expect(chat.getSnapshot()).toEqual({ messages: [], pending: false });
  });
});
