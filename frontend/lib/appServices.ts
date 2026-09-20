import { createAccountService } from "./account";
import { httpAccountApi } from "./accountApiHttp";
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
