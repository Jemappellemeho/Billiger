import { createEmptyState, ShoppingListState } from "./shoppingList";

type Listener = () => void;

/** The signed-in account's server copy of the list; only present while signed in. */
export type RemoteList = {
  save(state: ShoppingListState): Promise<void>;
};

type Persistence = {
  loadLocal(): ShoppingListState;
  saveLocal(state: ShoppingListState): void;
};

/**
 * A store outside React (not per-component state) so useSyncExternalStore
 * can give every caller the same list and match the SSR snapshot (empty, since
 * localStorage isn't reachable on the server) without a mount-time
 * setState-in-effect.
 *
 * Every change is kept locally (guest mode and offline cache). While a remote
 * is attached, changes are also pushed to it; `replace` is for state that came
 * *from* the server and so is never pushed back.
 */
export function createShoppingListStore({ loadLocal, saveLocal }: Persistence) {
  const listeners = new Set<Listener>();
  const serverSnapshot = createEmptyState();
  let cachedState: ShoppingListState | null = null;

  let remote: RemoteList | null = null;
  let dirty = false;
  let pushing: Promise<void> | null = null;

  function getSnapshot(): ShoppingListState {
    if (cachedState === null) cachedState = loadLocal();
    return cachedState;
  }

  function getServerSnapshot(): ShoppingListState {
    return serverSnapshot;
  }

  function subscribe(listener: Listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  function commit(next: ShoppingListState) {
    cachedState = next;
    saveLocal(next);
    listeners.forEach((listener) => listener());
  }

  /**
   * Pushes run one at a time and always send the newest state, so a slow
   * earlier request can never overwrite a later one on the server. A failed
   * push stays `dirty`; the next update sends the full latest state again.
   */
  function schedulePush() {
    dirty = true;
    if (!remote || pushing) return;
    pushing = (async () => {
      try {
        while (dirty && remote) {
          dirty = false;
          try {
            await remote.save(getSnapshot());
          } catch {
            dirty = true;
            return;
          }
        }
      } finally {
        pushing = null;
      }
    })();
  }

  return {
    getSnapshot,
    getServerSnapshot,
    subscribe,
    update(fn: (state: ShoppingListState) => ShoppingListState) {
      commit(fn(getSnapshot()));
      schedulePush();
    },
    replace(state: ShoppingListState) {
      commit(state);
    },
    attachRemote(next: RemoteList | null) {
      remote = next;
      dirty = false;
    },
    /** Resolves once every queued push has finished (for tests). */
    async settled() {
      while (pushing) await pushing;
    },
  };
}

export type ShoppingListStore = ReturnType<typeof createShoppingListStore>;
