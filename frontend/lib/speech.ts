/**
 * Voice input via the browser's SpeechRecognition (Chrome, Edge, Safari). The
 * browser does the speech-to-text, so the assistant only ever receives the
 * transcript. One utterance per press — there is no always-listening mode.
 */

type RecognitionResultEvent = { results: ArrayLike<ArrayLike<{ transcript: string }>> };

interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type RecognitionConstructor = new () => Recognition;

function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export function isSpeechInputSupported() {
  return recognitionConstructor() !== null;
}

export type SpeechHandlers = {
  onTranscript(text: string): void;
  onError(message: string): void;
  /** Listening is over, whether it produced a transcript, failed or was stopped. */
  onEnd(): void;
};

const ERROR_MESSAGES: Record<string, string> = {
  "not-allowed": "Der Zugriff auf das Mikrofon wurde nicht erlaubt.",
  "service-not-allowed": "Der Zugriff auf das Mikrofon wurde nicht erlaubt.",
  "no-speech": "Ich habe nichts gehört.",
  "audio-capture": "Es wurde kein Mikrofon gefunden.",
};

/** Starts listening; returns the controls for this utterance, or null if the browser can't. */
export function startSpeechInput({ onTranscript, onError, onEnd }: SpeechHandlers) {
  const Recognition = recognitionConstructor();
  if (!Recognition) return null;

  const recognition = new Recognition();
  recognition.lang = "de-AT";
  recognition.continuous = false;
  recognition.interimResults = false;

  let cancelled = false;
  recognition.onresult = (event) => {
    if (cancelled) return;
    const transcript = event.results[0]?.[0]?.transcript.trim();
    if (transcript) onTranscript(transcript);
  };
  recognition.onerror = (event) => {
    if (cancelled || event.error === "aborted") return;
    onError(ERROR_MESSAGES[event.error] ?? "Die Spracheingabe hat nicht funktioniert.");
  };
  recognition.onend = () => onEnd();

  recognition.start();

  return {
    /** Ends the utterance; the browser still delivers what it heard so far. */
    stop: () => recognition.stop(),
    /** Throws away whatever was heard (panel closed, component gone). */
    cancel: () => {
      cancelled = true;
      recognition.abort();
    },
  };
}
