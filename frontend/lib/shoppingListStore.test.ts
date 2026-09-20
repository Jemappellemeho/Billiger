import { describe, expect, test } from "vitest";
import { addItem, createEmptyState, ShoppingListState } from "./shoppingList";
import { createShoppingListStore } from "./shoppingListStore";

function setup(initial: ShoppingListState = createEmptyState()) {
  const local = { saved: initial };
  const store = createShoppingListStore({
    loadLocal: () => local.saved,
    saveLocal: (state) => {
      local.saved = state;
    },
  });
  const pushed: ShoppingListState[] = [];
  const remote = {
    failNext: false,
    save: async (state: ShoppingListState) => {
      if (remote.failNext) {
        remote.failNext = false;
        throw new Error("offline");
      }
      pushed.push(state);
    },
  };
  return { store, local, pushed, remote };
}

const milk = { name: "Milch", brand: "NÖM" };

describe("shopping list store", () => {
  test("an update is kept locally and does not touch any server as a guest", async () => {
    const { store, local, pushed } = setup();

    store.update((s) => addItem(s, milk));
    await store.settled();

    expect(store.getSnapshot().items).toHaveLength(1);
    expect(local.saved).toEqual(store.getSnapshot());
    expect(pushed).toEqual([]);
  });

  test("with a server attached, an update is kept locally and pushed to the server", async () => {
    const { store, local, pushed, remote } = setup();
    store.attachRemote(remote);

    store.update((s) => addItem(s, milk));
    await store.settled();

    expect(local.saved.items).toHaveLength(1);
    expect(pushed).toEqual([store.getSnapshot()]);
  });

  test("rapid updates end with the newest state on the server, never an older one", async () => {
    const { store, pushed, remote } = setup();
    store.attachRemote(remote);

    store.update((s) => addItem(s, { name: "Milch" }));
    store.update((s) => addItem(s, { name: "Brot" }));
    store.update((s) => addItem(s, { name: "Butter" }));
    await store.settled();

    expect(pushed.at(-1)?.items.map((i) => i.name)).toEqual(["Milch", "Brot", "Butter"]);
  });

  test("a failed push is retried with the full latest state on the next update", async () => {
    const { store, pushed, remote } = setup();
    store.attachRemote(remote);

    remote.failNext = true;
    store.update((s) => addItem(s, { name: "Milch" }));
    await store.settled();
    expect(pushed).toEqual([]);

    store.update((s) => addItem(s, { name: "Brot" }));
    await store.settled();

    expect(pushed.at(-1)?.items.map((i) => i.name)).toEqual(["Milch", "Brot"]);
  });

  test("replacing the list with server data is stored locally but not pushed back", async () => {
    const { store, local, pushed, remote } = setup();
    store.attachRemote(remote);
    const fromServer = addItem(createEmptyState(), milk);

    store.replace(fromServer);
    await store.settled();

    expect(store.getSnapshot()).toEqual(fromServer);
    expect(local.saved).toEqual(fromServer);
    expect(pushed).toEqual([]);
  });

  test("after detaching the server, updates stay local again", async () => {
    const { store, pushed, remote } = setup();
    store.attachRemote(remote);
    store.attachRemote(null);

    store.update((s) => addItem(s, milk));
    await store.settled();

    expect(pushed).toEqual([]);
  });

  test("subscribers are notified about updates and replacements", () => {
    const { store } = setup();
    let notifications = 0;
    store.subscribe(() => {
      notifications += 1;
    });

    store.update((s) => addItem(s, milk));
    store.replace(createEmptyState());

    expect(notifications).toBe(2);
  });

  test("the server-side snapshot is a stable empty list", () => {
    const { store } = setup(addItem(createEmptyState(), milk));

    expect(store.getServerSnapshot()).toEqual(createEmptyState());
    expect(store.getServerSnapshot()).toBe(store.getServerSnapshot());
  });
});
