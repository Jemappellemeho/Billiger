import { ShoppingListState } from "./shoppingList";

export type Session = { token: string; email: string };

export type AuthResult = { session: Session; list: ShoppingListState };

/** The backend calls the account service depends on (see backend/accounts). */
export type AccountApi = {
  register(email: string, password: string, guestList: ShoppingListState): Promise<AuthResult>;
  login(email: string, password: string, guestList: ShoppingListState): Promise<AuthResult>;
  google(idToken: string, guestList: ShoppingListState): Promise<AuthResult>;
  logout(token: string): Promise<void>;
  fetchList(token: string): Promise<ShoppingListState>;
  saveList(token: string, state: ShoppingListState): Promise<void>;
};

export class AccountError extends Error {}

/** The server no longer accepts the stored token (e.g. signed out on another device). */
export class UnauthorizedError extends AccountError {}
