import { AccountApi, Session, UnauthorizedError } from "./accountApi";
import { createEmptyState } from "./shoppingList";
import { ShoppingListStore } from "./shoppingListStore";

export type Credentials =
  | { kind: "register" | "login"; email: string; password: string }
  | { kind: "google"; idToken: string };

export type SessionPersistence = {
  load(): Session | null;
  save(session: Session): void;
  clear(): void;
};

type Listener = () => void;

/**
 * Ties the optional account to the shopping list store: signing in migrates
 * the guest list to the server and from then on the store pushes every change
 * there; signing out returns the device to an empty guest list.
 */
export function createAccountService({
  api,
  store,
  sessionPersistence,
}: {
  api: AccountApi;
  store: ShoppingListStore;
  sessionPersistence: SessionPersistence;
}) {
  const listeners = new Set<Listener>();
  // undefined = not read from storage yet (storage isn't reachable during SSR).
  let session: Session | null | undefined;

  function getSession(): Session | null {
    if (session === undefined) session = sessionPersistence.load();
    return session;
  }

  function setSession(next: Session | null) {
    session = next;
    if (next) sessionPersistence.save(next);
    else sessionPersistence.clear();
    listeners.forEach((listener) => listener());
  }

  function attachToServer(token: string) {
    store.attachRemote({ save: (state) => api.saveList(token, state) });
  }

  function detachFromServer() {
    store.attachRemote(null);
    store.replace(createEmptyState());
  }

  return {
    getSession,
    getServerSession: (): Session | null => null,
    subscribe(listener: Listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    async signIn(credentials: Credentials) {
      const guestList = store.getSnapshot();
      const { session: next, list } =
        credentials.kind === "google"
          ? await api.google(credentials.idToken, guestList)
          : credentials.kind === "register"
            ? await api.register(credentials.email, credentials.password, guestList)
            : await api.login(credentials.email, credentials.password, guestList);

      setSession(next);
      store.replace(list);
      attachToServer(next.token);
    },

    async signOut() {
      const current = getSession();
      setSession(null);
      detachFromServer();
      if (!current) return;
      try {
        await api.logout(current.token);
      } catch {
        // This device is signed out either way; the token stays valid on the
        // server until a later sign-out reaches it.
      }
    },

    /** Called once on app start: re-attach to the account and pull its list. */
    async restore() {
      const current = getSession();
      if (!current) return;
      try {
        store.replace(await api.fetchList(current.token));
      } catch (error) {
        if (error instanceof UnauthorizedError) {
          setSession(null);
          detachFromServer();
          return;
        }
        // Unreachable server: keep working from the local copy of the account's list.
      }
      attachToServer(current.token);
    },
  };
}

export type AccountService = ReturnType<typeof createAccountService>;
