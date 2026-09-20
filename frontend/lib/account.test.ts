import { describe, expect, test } from "vitest";
import { AccountApi, AuthResult, Session, UnauthorizedError } from "./accountApi";
import { createAccountService } from "./account";
import { addItem, createEmptyState, ShoppingListState } from "./shoppingList";
import { createShoppingListStore } from "./shoppingListStore";

const anna: Session = { token: "token-anna", email: "anna@example.com" };
const guestList = addItem(createEmptyState(), { name: "Brot" });
const serverList = addItem(addItem(createEmptyState(), { name: "Brot" }), { name: "Milch" });

function setup({
  guest = createEmptyState(),
  stored = null as Session | null,
}: { guest?: ShoppingListState; stored?: Session | null } = {}) {
  const local = { list: guest };
  const store = createShoppingListStore({
    loadLocal: () => local.list,
    saveLocal: (state) => {
      local.list = state;
    },
  });

  const calls: string[] = [];
  const server = { list: serverList, received: [] as ShoppingListState[], failWith: null as Error | null };
  const authResult = (): AuthResult => ({ session: anna, list: server.list });
  const guarded = async <T>(name: string, value: () => T): Promise<T> => {
    calls.push(name);
    if (server.failWith) throw server.failWith;
    return value();
  };
  const api: AccountApi = {
    register: (_e, _p, g) => guarded("register", () => (server.received.push(g), authResult())),
    login: (_e, _p, g) => guarded("login", () => (server.received.push(g), authResult())),
    google: (_t, g) => guarded("google", () => (server.received.push(g), authResult())),
    logout: (token) => guarded(`logout:${token}`, () => undefined),
    fetchList: (token) => guarded(`fetchList:${token}`, () => server.list),
    saveList: (token, state) =>
      guarded(`saveList:${token}`, () => {
        server.list = state;
      }),
  };

  const persisted = { session: stored };
  const service = createAccountService({
    api,
    store,
    sessionPersistence: {
      load: () => persisted.session,
      save: (s) => {
        persisted.session = s;
      },
      clear: () => {
        persisted.session = null;
      },
    },
  });
  return { service, store, server, calls, persisted, local };
}

const login = { kind: "login", email: "anna@example.com", password: "pw" } as const;

describe("account service", () => {
  test("signing in sends the guest list along and continues with the server's merged list", async () => {
    const { service, store, server, persisted } = setup({ guest: guestList });

    await service.signIn(login);

    expect(server.received).toEqual([guestList]);
    expect(store.getSnapshot()).toEqual(serverList);
    expect(service.getSession()).toEqual(anna);
    expect(persisted.session).toEqual(anna);
  });

  test("registering and Google sign-in use their own backend call", async () => {
    const registered = setup();
    await registered.service.signIn({ kind: "register", email: "a@b.at", password: "pw" });
    const google = setup();
    await google.service.signIn({ kind: "google", idToken: "jwt" });

    expect(registered.calls).toEqual(["register"]);
    expect(google.calls).toEqual(["google"]);
  });

  test("once signed in, list edits are saved to the account", async () => {
    const { service, store, server } = setup();
    await service.signIn(login);

    store.update((s) => addItem(s, { name: "Butter" }));
    await store.settled();

    expect(server.list.items.map((i) => i.name)).toEqual(["Brot", "Milch", "Butter"]);
  });

  test("a failed sign-in keeps the guest list and stays signed out", async () => {
    const { service, store, server, persisted } = setup({ guest: guestList });
    server.failWith = new Error("E-Mail oder Passwort ist falsch.");

    await expect(service.signIn(login)).rejects.toThrow("E-Mail oder Passwort ist falsch.");

    expect(store.getSnapshot()).toEqual(guestList);
    expect(service.getSession()).toBeNull();
    expect(persisted.session).toBeNull();
  });

  test("signing out revokes the token, empties the local list and stops syncing", async () => {
    const { service, store, server, calls, persisted, local } = setup();
    await service.signIn(login);

    await service.signOut();
    store.update((s) => addItem(s, { name: "Nach dem Logout" }));
    await store.settled();

    expect(calls).toContain("logout:token-anna");
    expect(service.getSession()).toBeNull();
    expect(persisted.session).toBeNull();
    expect(server.list).toEqual(serverList);
    expect(local.list.items.map((i) => i.name)).toEqual(["Nach dem Logout"]);
  });

  test("signing out still works locally when the server can't be reached", async () => {
    const { service, server, persisted } = setup();
    await service.signIn(login);
    server.failWith = new Error("offline");

    await service.signOut();

    expect(service.getSession()).toBeNull();
    expect(persisted.session).toBeNull();
  });

  test("restoring a stored session loads the account's list and syncs edits from then on", async () => {
    const { service, store, server } = setup({ stored: anna });

    await service.restore();
    store.update((s) => addItem(s, { name: "Butter" }));
    await store.settled();

    expect(service.getSession()).toEqual(anna);
    expect(server.list.items.map((i) => i.name)).toEqual(["Brot", "Milch", "Butter"]);
  });

  test("restoring with a token the server rejects signs out and clears the account's local copy", async () => {
    const { service, store, server, persisted } = setup({ guest: serverList, stored: anna });
    server.failWith = new UnauthorizedError("Token ungültig");

    await service.restore();

    expect(service.getSession()).toBeNull();
    expect(persisted.session).toBeNull();
    expect(store.getSnapshot()).toEqual(createEmptyState());
  });

  test("restoring while the server is unreachable keeps the session and the local copy", async () => {
    const { service, store, server } = setup({ guest: guestList, stored: anna });
    server.failWith = new Error("offline");

    await service.restore();

    expect(service.getSession()).toEqual(anna);
    expect(store.getSnapshot()).toEqual(guestList);
  });

  test("restoring without a stored session does nothing", async () => {
    const { service, calls } = setup({ guest: guestList });

    await service.restore();

    expect(calls).toEqual([]);
    expect(service.getSession()).toBeNull();
  });
});
