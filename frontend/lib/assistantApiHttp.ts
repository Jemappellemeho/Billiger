import { API_BASE_URL } from "./api";
import { AssistantApi, AssistantError, ChatAnswer, ChatRequest } from "./assistantApi";

async function failure(response: Response): Promise<AssistantError> {
  if (response.status === 401) {
    return new AssistantError("Für den Assistenten musst du dich anmelden.");
  }
  if (response.status === 429) {
    return new AssistantError("Einen Moment bitte — du schreibst zu schnell.");
  }
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
  return new AssistantError(
    typeof body.detail === "string"
      ? body.detail
      : `Der Assistent hat nicht geantwortet (${response.status}).`
  );
}

export const httpAssistantApi: AssistantApi = {
  async chat({ token, message, input, history, location }: ChatRequest): Promise<ChatAnswer> {
    const body: Record<string, unknown> = { message, input, history };
    if (location && "zipCode" in location) {
      body.zip_code = location.zipCode;
    } else if (location) {
      body.lat = location.lat;
      body.lon = location.lon;
    }

    const response = await fetch(`${API_BASE_URL}/api/assistant/chat/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Token ${token}` },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw await failure(response);

    const answer = (await response.json()) as ChatAnswer;
    return { reply: answer.reply, actions: answer.actions };
  },
};
