import { fromWire, WireList } from "./accountApiHttp";
import { API_BASE_URL } from "./api";
import {
  AssistantApi,
  AssistantError,
  ChatAnswer,
  ChatRequest,
  Proposal,
  ProposalOutcome,
} from "./assistantApi";

async function failure(response: Response): Promise<AssistantError> {
  if (response.status === 401) {
    return new AssistantError("Für den Assistenten musst du dich anmelden.", 401);
  }
  if (response.status === 429) {
    return new AssistantError("Einen Moment bitte — du schreibst zu schnell.", 429);
  }
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
  return new AssistantError(
    typeof body.detail === "string"
      ? body.detail
      : `Der Assistent hat nicht geantwortet (${response.status}).`,
    response.status
  );
}

async function send<T>(
  path: string,
  { method, token, body }: { method: "GET" | "POST" | "PUT"; token: string; body?: unknown }
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/assistant/${path}`, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Token ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as T;
}

type OutcomeResponse = {
  proposal: Proposal;
  message: string;
  shopping_list?: WireList;
  location?: { zip_code: string };
};

export const httpAssistantApi: AssistantApi = {
  async chat({ token, message, input, history, location }: ChatRequest): Promise<ChatAnswer> {
    const body: Record<string, unknown> = { message, input, history };
    if (location && "zipCode" in location) {
      body.zip_code = location.zipCode;
    } else if (location) {
      body.lat = location.lat;
      body.lon = location.lon;
    }

    const answer = await send<ChatAnswer>("chat/", { method: "POST", token, body });
    return { reply: answer.reply, actions: answer.actions, proposals: answer.proposals ?? [] };
  },

  async openProposals(token) {
    const response = await send<{ proposals: Proposal[] }>("proposals/", { method: "GET", token });
    return response.proposals;
  },

  async decide(token, proposalId, decision): Promise<ProposalOutcome> {
    const response = await send<OutcomeResponse>(`proposals/${proposalId}/${decision}/`, {
      method: "POST",
      token,
    });
    return {
      proposal: response.proposal,
      message: response.message,
      shoppingList: response.shopping_list ? fromWire(response.shopping_list) : undefined,
      location: response.location ? { zipCode: response.location.zip_code } : undefined,
    };
  },

  async revise(token, proposalId, changes) {
    const response = await send<{ proposal: Proposal }>(`proposals/${proposalId}/`, {
      method: "PUT",
      token,
      body: changes,
    });
    return response.proposal;
  },
};
