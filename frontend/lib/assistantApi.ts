import type { SearchLocation } from "./api";

/** Wire format of POST /api/assistant/chat/ (see backend/assistant/views.py). */
export type ChatInput = "text" | "voice";

export type ApiHistoryMessage = { role: "user" | "assistant"; content: string };

export type ChatRequest = {
  token: string;
  message: string;
  /** How the message was entered; a voice message is already transcribed text. */
  input: ChatInput;
  history: ApiHistoryMessage[];
  /** Where prices are looked up for; null while the location is still unknown. */
  location: SearchLocation | null;
};

/** What the assistant looked up to answer, e.g. the shopping list or the savings summary. */
export type AssistantAction = { tool: string; input: unknown; result: unknown };

export type ChatAnswer = { reply: string; actions: AssistantAction[] };

/** A failure with a message that can be shown to the user as is. */
export class AssistantError extends Error {}

export interface AssistantApi {
  chat(request: ChatRequest): Promise<ChatAnswer>;
}
