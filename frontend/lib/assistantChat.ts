import { ApiHistoryMessage, AssistantApi, AssistantError, ChatInput } from "./assistantApi";
import type { SearchLocation } from "./api";

type Listener = () => void;

export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  /** How a user message was entered; a spoken one is shown as transcribed. */
  input: ChatInput;
  /** An error notice rather than something the assistant said; never sent back as history. */
  failed: boolean;
};

export type AssistantChatState = { messages: ChatMessage[]; pending: boolean };

export type SendContext = {
  token: string;
  location: SearchLocation | null;
  input?: ChatInput;
};

// Limits the backend enforces (backend/assistant/serializers.py).
export const MAX_HISTORY_MESSAGES = 40;
export const MAX_MESSAGE_LENGTH = 2000;
const MAX_HISTORY_CONTENT_LENGTH = 4000;

const UNREACHABLE = "Der Assistent ist gerade nicht erreichbar.";
const NO_ANSWER = "Dazu habe ich gerade keine Antwort.";

const emptyState: AssistantChatState = { messages: [], pending: false };

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
 */
export function createAssistantChat({ api }: { api: AssistantApi }) {
  const listeners = new Set<Listener>();
  let state: AssistantChatState = emptyState;
  let nextId = 1;
  // Bumped by reset() so an answer that was in flight for the old conversation is dropped.
  let generation = 0;

  function commit(next: AssistantChatState) {
    state = next;
    listeners.forEach((listener) => listener());
  }

  function addMessage(message: Omit<ChatMessage, "id">, pending: boolean) {
    commit({ messages: [...state.messages, { ...message, id: nextId++ }], pending });
  }

  async function send(text: string, { token, location, input = "text" }: SendContext) {
    const message = text.trim().slice(0, MAX_MESSAGE_LENGTH);
    if (!message || state.pending) return;

    const history = buildHistory(state.messages);
    const conversation = generation;
    addMessage({ role: "user", content: message, input, failed: false }, true);

    let reply: Omit<ChatMessage, "id">;
    try {
      const answer = await api.chat({ token, message, input, history, location });
      reply = { role: "assistant", content: answer.reply.trim() || NO_ANSWER, input: "text", failed: false };
    } catch (error) {
      const content = error instanceof AssistantError ? error.message : UNREACHABLE;
      reply = { role: "assistant", content, input: "text", failed: true };
    }

    if (conversation === generation) addMessage(reply, false);
  }

  function reset() {
    generation++;
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
    reset,
  };
}
