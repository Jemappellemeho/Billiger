"use client";

import { useEffect, useRef } from "react";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
const SCRIPT_SRC = "https://accounts.google.com/gsi/client";

type GoogleIdentity = {
  accounts: {
    id: {
      initialize(config: { client_id: string; callback: (r: { credential: string }) => void }): void;
      renderButton(element: HTMLElement, options: Record<string, string>): void;
    };
  };
};

declare global {
  interface Window {
    google?: GoogleIdentity;
  }
}

/** Google Identity Services button; renders nothing until a client ID is configured. */
export function GoogleSignInButton({ onCredential }: { onCredential: (idToken: string) => void }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!CLIENT_ID || !container.current) return;
    const element = container.current;

    function render() {
      if (!window.google || !CLIENT_ID) return;
      window.google.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: ({ credential }) => onCredential(credential),
      });
      window.google.accounts.id.renderButton(element, { theme: "outline", size: "large" });
    }

    if (window.google) {
      render();
      return;
    }

    let script = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
    if (!script) {
      script = document.createElement("script");
      script.src = SCRIPT_SRC;
      script.async = true;
      document.head.appendChild(script);
    }
    script.addEventListener("load", render);
    return () => script.removeEventListener("load", render);
  }, [onCredential]);

  if (!CLIENT_ID) return null;
  return <div ref={container} />;
}
