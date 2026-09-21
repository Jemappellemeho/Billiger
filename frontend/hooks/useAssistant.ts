"use client";

import { useSyncExternalStore } from "react";
import { assistantChat } from "@/lib/appServices";

export function useAssistant() {
  const { messages, pending } = useSyncExternalStore(
    assistantChat.subscribe,
    assistantChat.getSnapshot,
    assistantChat.getServerSnapshot
  );

  return {
    messages,
    pending,
    send: assistantChat.send,
    decide: assistantChat.decide,
    revise: assistantChat.revise,
    reset: assistantChat.reset,
  };
}
