"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchStreakSummary } from "@/lib/api";
import { StreakSummary } from "@/lib/streak";

/**
 * The signed-in account's streak & savings summary. Guests (no token) have
 * none. `refresh` re-reads it, e.g. right after a comparison completed.
 * The hero is a nicety, so a failed load simply leaves it hidden.
 */
export function useStreak(token: string | null) {
  const [loaded, setLoaded] = useState<{ token: string; summary: StreakSummary } | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    fetchStreakSummary(token)
      .then((summary) => {
        if (!cancelled) setLoaded({ token, summary });
      })
      .catch(() => {
        // keep whatever we showed before
      });
    return () => {
      cancelled = true;
    };
  }, [token, reloads]);

  const refresh = useCallback(() => setReloads((count) => count + 1), []);

  // Never show another account's numbers after signing out or switching account.
  const summary = token && loaded?.token === token ? loaded.summary : null;
  return { summary, refresh };
}
