"use client";

import { useEffect } from "react";

export function ServiceWorkerRegistration() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // PWA installability is a progressive enhancement — search still
        // works without it, so a failed registration is silently ignored.
      });
    }
  }, []);

  return null;
}
