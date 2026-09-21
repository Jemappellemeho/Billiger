import { createAccountService } from "./account";
import { httpAccountApi } from "./accountApiHttp";
import { httpAssistantApi } from "./assistantApiHttp";
import { createAssistantChat } from "./assistantChat";
import { clearSession, loadSession, saveSession } from "./sessionStorage";
import { createShoppingListStore } from "./shoppingListStore";
import { loadState, saveState } from "./shoppingListStorage";

/** The app's single shopping list and account, shared by every component. */
export const shoppingListStore = createShoppingListStore({
  loadLocal: loadState,
  saveLocal: saveState,
});

export const accountService = createAccountService({
  api: httpAccountApi,
  store: shoppingListStore,
  sessionPersistence: { load: loadSession, save: saveSession, clear: clearSession },
});

/** The built-in assistant's conversation, shared by the floating button and its panel. */
export const assistantChat = createAssistantChat({
  api: httpAssistantApi,
  // An accepted list or preference change comes from the server, so it is shown, not pushed back.
  applyList: (list) => shoppingListStore.replace(list),
});
