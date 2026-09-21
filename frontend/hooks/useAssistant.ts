"use client";

import { useSyncExternalStore } from "react";
import { assistantChat } from "@/lib/appServices";

export function useAssistant() {
  const { messages, pending, inbox } = useSyncExternalStore(
    assistantChat.subscribe,
    assistantChat.getSnapshot,
    assistantChat.getServerSnapshot
  );

  return {
    messages,
    pending,
    inbox,
    send: assistantChat.send,
    loadOpenProposals: assistantChat.loadOpenProposals,
    decide: assistantChat.decide,
    revise: assistantChat.revise,
    reset: assistantChat.reset,
  };
}
