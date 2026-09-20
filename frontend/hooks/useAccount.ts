"use client";

import { useSyncExternalStore } from "react";
import { accountService } from "@/lib/appServices";

export function useAccount() {
  const session = useSyncExternalStore(
    accountService.subscribe,
    accountService.getSession,
    accountService.getServerSession
  );

  return { session, signIn: accountService.signIn, signOut: accountService.signOut };
}
