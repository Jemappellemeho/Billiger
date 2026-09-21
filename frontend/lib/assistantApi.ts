import type { SearchLocation } from "./api";
import type { ShoppingListItem, ShoppingListState } from "./shoppingList";

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

/**
 * A change the assistant suggests (backend/assistant/proposals.py). It is only a suggestion: the
 * `diff` shows in full what would change, and nothing is applied until the user accepts.
 * "stale" = the list changed before the user decided, so the proposal can no longer be applied.
 */
export type ProposalStatus = "pending" | "accepted" | "rejected" | "stale";

type ProposalBase = { id: number; status: ProposalStatus };

export type ItemRef = { id: string; name: string; brand: string | null };

export type ShoppingListProposal = ProposalBase & {
  kind: "shopping_list";
  diff: {
    added: ShoppingListItem[];
    removed: ShoppingListItem[];
    changed: (ItemRef & {
      changes: {
        quantity?: { before: number; after: number };
        category?: { before: string | null; after: string | null };
      };
    })[];
    unchanged: ShoppingListItem[];
  };
  /** The complete new list. */
  proposed: { items: ShoppingListItem[] };
};

export type PreferenceListKey = "preferred_brands" | "excluded_ingredients" | "excluded_stores";

export type PreferencesProposal = ProposalBase & {
  kind: "preferences";
  /** Only the parts that change. */
  diff: Partial<Record<PreferenceListKey, { added: string[]; removed: string[] }>> & {
    favorites?: { added: ItemRef[]; removed: ItemRef[] };
  };
  /** The complete new state of each part the proposal touches; favorites are item ids. */
  proposed: Partial<Record<PreferenceListKey, string[]>> & { favorite_items?: string[] };
};

export type LocationProposal = ProposalBase & {
  kind: "location";
  diff: { before: { zip_code: string } | null; after: { zip_code: string } };
  proposed: { zip_code: string };
};

export type Proposal = ShoppingListProposal | PreferencesProposal | LocationProposal;

/** An edited proposal, in the shape of `Proposal["proposed"]` ("Ändern"). */
export type ProposalChanges = Record<string, unknown>;

export type ChatAnswer = { reply: string; actions: AssistantAction[]; proposals: Proposal[] };

export type ProposalDecision = "accept" | "reject";

/** What the user's decision led to: the confirmation to show, and what to apply on this device. */
export type ProposalOutcome = {
  proposal: Proposal;
  message: string;
  /** The account's list after accepting a list or preference change. */
  shoppingList?: ShoppingListState;
  /** The new location after accepting a location change; it lives in the client. */
  location?: { zipCode: string };
};

/** A failure with a message that can be shown to the user as is. */
export class AssistantError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

export interface AssistantApi {
  chat(request: ChatRequest): Promise<ChatAnswer>;
  /** The account's proposals still waiting for a decision, newest first (also ones an external client made). */
  openProposals(token: string): Promise<Proposal[]>;
  decide(token: string, proposalId: number, decision: ProposalDecision): Promise<ProposalOutcome>;
  revise(token: string, proposalId: number, changes: ProposalChanges): Promise<Proposal>;
}
