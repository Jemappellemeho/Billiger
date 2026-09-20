"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useAssistant } from "@/hooks/useAssistant";
import type { SearchLocation } from "@/lib/api";
import { MAX_MESSAGE_LENGTH } from "@/lib/assistantChat";
import { isSpeechInputSupported, startSpeechInput } from "@/lib/speech";
import styles from "./AssistantWidget.module.css";

const SUGGESTIONS = [
  "Wo ist Milch gerade am billigsten?",
  "Was steht auf meiner Einkaufsliste?",
  "Fass meinen Warenkorb-Vergleich zusammen.",
  "Wie steht es um meine Ersparnis?",
];

const noSubscription = () => () => {};

type Listening = { stop(): void; cancel(): void };

/**
 * The built-in assistant: a floating button that opens a chat panel. Needs an
 * account (guests only get a hint). Typed and spoken messages take the same
 * path; a spoken one shows up as a transcribed bubble before the answer.
 */
export function AssistantWidget({
  token,
  location,
}: {
  token: string | null;
  location: SearchLocation | null;
}) {
  const { messages, pending, send, reset } = useAssistant();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const speechSupported = useSyncExternalStore(noSubscription, isSpeechInputSupported, () => false);

  const microphone = useRef<Listening | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);

  // Another account (or none) must never see the previous conversation, nor receive what is
  // still being said into the microphone.
  useEffect(() => {
    microphone.current?.cancel();
    reset();
  }, [token, reset]);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, pending, open]);

  // Nothing keeps listening once the panel is closed or gone.
  useEffect(() => {
    if (!open) microphone.current?.cancel();
  }, [open]);
  useEffect(() => () => microphone.current?.cancel(), []);

  function submit(text: string, spoken = false) {
    if (!token) return;
    void send(text, { token, location, input: spoken ? "voice" : "text" });
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit(draft);
    setDraft("");
  }

  function toggleVoice() {
    if (listening) {
      microphone.current?.stop();
      return;
    }
    setVoiceError(null);
    let session: Listening | null = null;
    session = startSpeechInput({
      onTranscript: (transcript) => submit(transcript, true),
      onError: setVoiceError,
      onEnd: () => {
        // A cancelled session can end after a newer one has started; only the current one may reset.
        if (microphone.current !== session) return;
        microphone.current = null;
        setListening(false);
      },
    });
    if (session) {
      microphone.current = session;
      setListening(true);
    } else {
      setVoiceError("Spracheingabe wird von diesem Browser nicht unterstützt.");
    }
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") setOpen(false);
  }

  if (!open) {
    return (
      <button
        type="button"
        className={styles.launcher}
        onClick={() => setOpen(true)}
        aria-label="Assistent öffnen"
      >
        <span aria-hidden="true">💬</span>
      </button>
    );
  }

  return (
    <section
      className={styles.panel}
      role="dialog"
      aria-label="Assistent"
      onKeyDown={handleKeyDown}
    >
      <header className={styles.header}>
        <h2>Assistent</h2>
        <button
          type="button"
          className={styles.close}
          onClick={() => setOpen(false)}
          aria-label="Assistent schließen"
        >
          ✕
        </button>
      </header>

      <div className={styles.messages} role="log" aria-live="polite">
        {!token && (
          <p className={styles.hint}>
            Der Assistent ist nur mit Konto verfügbar. Melde dich an oder registriere dich, um ihn zu
            nutzen.
          </p>
        )}

        {token && messages.length === 0 && (
          <div className={styles.suggestions}>
            <p className={styles.hint}>Frag mich zu Preisen, deiner Liste oder deiner Ersparnis:</p>
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className={styles.suggestion}
                disabled={pending}
                onClick={() => submit(suggestion)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`${styles.bubble} ${
              message.role === "user" ? styles.user : message.failed ? styles.failed : styles.assistant
            }`}
          >
            {message.role === "user" && message.input === "voice" && (
              <span className={styles.voiceLabel}>🎤 per Spracheingabe transkribiert</span>
            )}
            {message.content}
          </div>
        ))}

        {pending && (
          <div className={`${styles.bubble} ${styles.assistant} ${styles.typing}`}>Einen Moment …</div>
        )}
        <div ref={end} />
      </div>

      {(listening || voiceError) && (
        <p className={styles.voiceStatus} role="status">
          {listening ? "Ich höre zu … tippe das Mikrofon, wenn du fertig bist." : voiceError}
        </p>
      )}

      <form className={styles.composer} onSubmit={handleSubmit}>
        <input
          ref={input}
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Nachricht an den Assistenten"
          aria-label="Nachricht"
          maxLength={MAX_MESSAGE_LENGTH}
          disabled={!token}
        />
        {speechSupported && (
          <button
            type="button"
            className={listening ? `${styles.mic} ${styles.micActive}` : styles.mic}
            onClick={toggleVoice}
            disabled={!token || (pending && !listening)}
            aria-label={listening ? "Spracheingabe beenden" : "Spracheingabe starten"}
            aria-pressed={listening}
          >
            🎤
          </button>
        )}
        <button type="submit" className={styles.send} disabled={!token || pending || !draft.trim()}>
          Senden
        </button>
      </form>
    </section>
  );
}
