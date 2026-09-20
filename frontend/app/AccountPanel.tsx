"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAccount } from "@/hooks/useAccount";
import { AccountError } from "@/lib/accountApi";
import { accountService } from "@/lib/appServices";
import { GoogleSignInButton } from "./GoogleSignInButton";
import styles from "./AccountPanel.module.css";

type Mode = "login" | "register";

export function AccountPanel() {
  const { session, signIn, signOut } = useAccount();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void accountService.restore();
  }, []);

  const submitCredentials = useCallback(
    async (credentials: Parameters<typeof signIn>[0]) => {
      setError(null);
      setBusy(true);
      try {
        await signIn(credentials);
        setPassword("");
      } catch (err) {
        setError(err instanceof AccountError ? err.message : "Etwas ist schiefgelaufen.");
      } finally {
        setBusy(false);
      }
    },
    [signIn]
  );

  const handleGoogleCredential = useCallback(
    (idToken: string) => void submitCredentials({ kind: "google", idToken }),
    [submitCredentials]
  );

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void submitCredentials({ kind: mode, email: email.trim(), password });
  }

  if (session) {
    return (
      <section className={styles.panel}>
        <p>
          Angemeldet als <strong>{session.email}</strong> — deine Liste wird im Konto gespeichert.
        </p>
        <button type="button" onClick={() => void signOut()}>
          Abmelden
        </button>
      </section>
    );
  }

  return (
    <section className={styles.panel}>
      <p className={styles.hint}>
        Ohne Konto bleibt deine Liste nur auf diesem Gerät. Mit Konto wird sie gespeichert und beim
        ersten Anmelden übernommen.
      </p>
      <form onSubmit={handleSubmit} className={styles.form}>
        <input
          type="email"
          autoComplete="email"
          placeholder="E-Mail"
          aria-label="E-Mail"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          placeholder="Passwort"
          aria-label="Passwort"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button type="submit" disabled={busy}>
          {mode === "login" ? "Anmelden" : "Registrieren"}
        </button>
      </form>
      <button
        type="button"
        className={styles.link}
        onClick={() => setMode(mode === "login" ? "register" : "login")}
      >
        {mode === "login" ? "Noch kein Konto? Registrieren" : "Schon ein Konto? Anmelden"}
      </button>
      <GoogleSignInButton onCredential={handleGoogleCredential} />
      {error && <p className={styles.error}>{error}</p>}
    </section>
  );
}
