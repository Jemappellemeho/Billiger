import {
  ApiHistoryMessage,
  AssistantApi,
  AssistantError,
  ChatInput,
  Proposal,
  ProposalChanges,
  ProposalDecision,
} from "./assistantApi";
import type { SearchLocation } from "./api";
import type { ShoppingListState } from "./shoppingList";

type Listener = () => void;

/** A proposal in the conversation: the suggestion itself plus what the user is doing with it. */
export type ChatProposal = {
  proposal: Proposal;
  /** A decision or edit is on its way to the server. */
  busy: boolean;
  /** Why the last decision or edit didn't work, in words for the user. */
  error: string | null;
};

export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  /** How a user message was entered; a spoken one is shown as transcribed. */
  input: ChatInput;
  /** An error notice rather than something the assistant said; never sent back as history. */
  failed: boolean;
  /** Changes the assistant suggested with this message; each waits for the user's decision. */
  proposals: ChatProposal[];
};

export type AssistantChatState = {
  messages: ChatMessage[];
  pending: boolean;
  /**
   * Open proposals that no chat turn of this conversation made, e.g. ones an external
   * assistant (MCP) created; loaded from the server, newest first.
   */
  inbox: ChatProposal[];
};

export type SendContext = {
  token: string;
  location: SearchLocation | null;
  input?: ChatInput;
};

export type DecideContext = {
  token: string;
  /** Called with the new PLZ when a location change is accepted (the location lives in the client). */
  onLocationChange?: (zipCode: string) => void;
};

// Limits the backend enforces (backend/assistant/serializers.py).
export const MAX_HISTORY_MESSAGES = 40;
export const MAX_MESSAGE_LENGTH = 2000;
const MAX_HISTORY_CONTENT_LENGTH = 4000;

const UNREACHABLE = "Der Assistent ist gerade nicht erreichbar.";
const CONFLICT = 409;

const emptyState: AssistantChatState = { messages: [], pending: false, inbox: [] };

function buildHistory(messages: ChatMessage[]): ApiHistoryMessage[] {
  const history = messages
    .filter((message) => !message.failed)
    .slice(-MAX_HISTORY_MESSAGES)
    .map(({ role, content }) => ({ role, content: content.slice(0, MAX_HISTORY_CONTENT_LENGTH) }));
  // The backend wants the conversation to open with the user's turn.
  while (history.length > 0 && history[0].role !== "user") history.shift();
  return history;
}

/**
 * The built-in assistant's conversation, held outside React so the floating
 * button and the panel share it (same shape as the shopping-list store).
 *
 * Text and voice take one path: a spoken message is transcribed by the
 * browser and arrives here as text with `input: "voice"`, which only changes
 * how its bubble is labelled. The conversation is not persisted.
 *
 * The assistant only ever *proposes* changes. A proposal comes with its full
 * diff and stays open until the user accepts, edits or rejects it; only
 * accepting changes anything, and every decision ends in a short confirmation
 * message. `applyList` is how an accepted list or preference change reaches the
 * app's shopping list (server state, so it is never pushed back).
 */
export function createAssistantChat({
  api,
  applyList = () => {},
}: {
  api: AssistantApi;
  applyList?: (state: ShoppingListState) => void;
}) {
  const listeners = new Set<Listener>();
  let state: AssistantChatState = emptyState;
  let nextId = 1;
  // Bumped by reset() so an answer that was in flight for the old conversation is dropped.
  let generation = 0;
  // Bumped by every load and by every decision or edit, so a load answered after either is dropped
  // instead of overwriting what the user just did with what the server knew before.
  let inboxVersion = 0;

  function commit(next: AssistantChatState) {
    state = next;
    listeners.forEach((listener) => listener());
  }

  function addMessage(message: Omit<ChatMessage, "id">, pending: boolean) {
    commit({ ...state, messages: [...state.messages, { ...message, id: nextId++ }], pending });
  }

  function findProposal(proposalId: number) {
    for (const message of state.messages) {
      const found = message.proposals.find((entry) => entry.proposal.id === proposalId);
      if (found) return found;
    }
    return state.inbox.find((entry) => entry.proposal.id === proposalId);
  }

  function updateProposal(proposalId: number, change: (entry: ChatProposal) => ChatProposal) {
    const apply = (entry: ChatProposal) => (entry.proposal.id === proposalId ? change(entry) : entry);
    commit({
      ...state,
      messages: state.messages.map((message) => ({ ...message, proposals: message.proposals.map(apply) })),
      inbox: state.inbox.map(apply),
    });
  }

  const isListed = (proposalId: number) => state.inbox.some((entry) => entry.proposal.id === proposalId);

  function dropFromInbox(proposalId: number) {
    inboxVersion++;
    commit({ ...state, inbox: state.inbox.filter((entry) => entry.proposal.id !== proposalId) });
  }

  /**
   * A failed decision or edit stays on the proposal; a 409 means it can't be applied any more.
   * In the chat it is then marked as such; a listed one leaves the list, with the reason as a notice.
   */
  function failProposal(proposalId: number, error: unknown) {
    const message = error instanceof AssistantError ? error.message : UNREACHABLE;
    const conflict = error instanceof AssistantError && error.status === CONFLICT;
    if (conflict && isListed(proposalId)) {
      dropFromInbox(proposalId);
      addMessage({ role: "assistant", content: message, input: "text", failed: true, proposals: [] }, state.pending);
      return;
    }
    updateProposal(proposalId, (entry) => ({
      ...entry,
      busy: false,
      error: message,
      proposal: conflict && entry.proposal.status === "pending" ? { ...entry.proposal, status: "stale" } : entry.proposal,
    }));
  }

  async function send(text: string, { token, location, input = "text" }: SendContext) {
    const message = text.trim().slice(0, MAX_MESSAGE_LENGTH);
    if (!message || state.pending) return;

    const history = buildHistory(state.messages);
    const conversation = generation;
    addMessage({ role: "user", content: message, input, failed: false, proposals: [] }, true);

    let reply: Omit<ChatMessage, "id">;
    try {
      const answer = await api.chat({ token, message, input, history, location });
      reply = {
        role: "assistant",
        content: answer.reply,
        input: "text",
        failed: false,
        proposals: answer.proposals.map((proposal) => ({ proposal, busy: false, error: null })),
      };
    } catch (error) {
      const content = error instanceof AssistantError ? error.message : UNREACHABLE;
      reply = { role: "assistant", content, input: "text", failed: true, proposals: [] };
    }

    if (conversation !== generation) return;
    // A proposal this turn made may already have been loaded into the inbox: the chat takes it over.
    const made = new Set(reply.proposals.map((entry) => entry.proposal.id));
    if (state.inbox.some((entry) => made.has(entry.proposal.id))) {
      inboxVersion++;
      commit({ ...state, inbox: state.inbox.filter((entry) => !made.has(entry.proposal.id)) });
    }
    addMessage(reply, false);
  }

  /**
   * Refreshes the inbox from the server: what the account still has open, minus what the chat already
   * shows (matched by id). What was decided elsewhere drops out; a decision or edit that is on its way
   * stays until it settles. Only the newest load counts, and none that a decision or edit overtook.
   * This is a background refresh, so a failure leaves the list as it was.
   */
  async function loadOpenProposals(token: string) {
    const conversation = generation;
    const version = ++inboxVersion;
    let open: Proposal[];
    try {
      open = await api.openProposals(token);
    } catch {
      return;
    }
    if (conversation !== generation || version !== inboxVersion) return;

    const inChat = new Set(state.messages.flatMap((message) => message.proposals.map((entry) => entry.proposal.id)));
    const known = new Map(state.inbox.map((entry) => [entry.proposal.id, entry]));
    const listed = open
      .filter((proposal) => !inChat.has(proposal.id))
      .map((proposal) => {
        const entry = known.get(proposal.id);
        return entry?.busy ? entry : { ...(entry ?? { busy: false, error: null }), proposal };
      });
    const inFlight = state.inbox.filter(
      (entry) => entry.busy && !listed.some((other) => other.proposal.id === entry.proposal.id)
    );
    commit({ ...state, inbox: [...listed, ...inFlight] });
  }

  /** "Übernehmen" / "Verwerfen": decides an open proposal and shows the confirmation. */
  async function decide(
    proposalId: number,
    decision: ProposalDecision,
    { token, onLocationChange }: DecideContext
  ) {
    const open = findProposal(proposalId);
    if (!open || open.busy || open.proposal.status !== "pending") return;

    const conversation = generation;
    updateProposal(proposalId, (entry) => ({ ...entry, busy: true, error: null }));
    try {
      const outcome = await api.decide(token, proposalId, decision);
      // Another account's (or a reset) conversation must not receive this account's changes.
      if (conversation !== generation) return;

      if (outcome.shoppingList) applyList(outcome.shoppingList);
      if (outcome.location) onLocationChange?.(outcome.location.zipCode);
      // A decided listed proposal leaves the list; its confirmation message is all that remains.
      if (isListed(proposalId)) {
        dropFromInbox(proposalId);
      } else {
        updateProposal(proposalId, () => ({ proposal: outcome.proposal, busy: false, error: null }));
      }
      addMessage(
        { role: "assistant", content: outcome.message, input: "text", failed: false, proposals: [] },
        state.pending
      );
    } catch (error) {
      if (conversation === generation) failProposal(proposalId, error);
    }
  }

  /** "Ändern": replaces the proposed state with the user's edit and shows the fresh diff. */
  async function revise(proposalId: number, changes: ProposalChanges, { token }: { token: string }) {
    const open = findProposal(proposalId);
    if (!open || open.busy || open.proposal.status !== "pending") return false;

    const conversation = generation;
    updateProposal(proposalId, (entry) => ({ ...entry, busy: true, error: null }));
    try {
      const proposal = await api.revise(token, proposalId, changes);
      if (conversation !== generation) return false;
      inboxVersion++;
      updateProposal(proposalId, () => ({ proposal, busy: false, error: null }));
      return true;
    } catch (error) {
      if (conversation === generation) failProposal(proposalId, error);
      return false;
    }
  }

  function reset() {
    generation++;
    inboxVersion++;
    commit(emptyState);
  }

  return {
    getSnapshot: () => state,
    getServerSnapshot: () => emptyState,
    subscribe(listener: Listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    send,
    loadOpenProposals,
    decide,
    revise,
    reset,
  };
}
