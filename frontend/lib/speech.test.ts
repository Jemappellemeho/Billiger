import { afterEach, describe, expect, test, vi } from "vitest";
import { isSpeechInputSupported, startSpeechInput } from "./speech";

/** A stand-in for the browser's SpeechRecognition that the test drives by hand. */
class FakeRecognition {
  static last: FakeRecognition;
  lang = "";
  continuous = true;
  interimResults = true;
  started = false;
  stopped = false;
  aborted = false;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;

  constructor() {
    FakeRecognition.last = this;
  }
  start() {
    this.started = true;
  }
  stop() {
    this.stopped = true;
    this.onend?.();
  }
  abort() {
    this.aborted = true;
    this.onerror?.({ error: "aborted" });
  }
  hear(transcript: string) {
    this.onresult?.({ results: [[{ transcript }]] });
    this.onend?.();
  }
}

function handlers() {
  return { onTranscript: vi.fn(), onError: vi.fn(), onEnd: vi.fn() };
}

afterEach(() => vi.unstubAllGlobals());

describe("speech input", () => {
  test("is unsupported without a browser SpeechRecognition", () => {
    expect(isSpeechInputSupported()).toBe(false);
    expect(startSpeechInput(handlers())).toBeNull();
  });

  test("listens for one German utterance, not continuously", () => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);

    expect(isSpeechInputSupported()).toBe(true);
    startSpeechInput(handlers());

    expect(FakeRecognition.last).toMatchObject({ started: true, lang: "de-AT", continuous: false, interimResults: false });
  });

  test("also works with the prefixed constructor (Safari, older Chromium)", () => {
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);

    expect(startSpeechInput(handlers())).not.toBeNull();
  });

  test("hands over the transcript, then reports the end", () => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    const h = handlers();
    startSpeechInput(h);

    FakeRecognition.last.hear("  Wo ist Milch am billigsten?  ");

    expect(h.onTranscript).toHaveBeenCalledWith("Wo ist Milch am billigsten?");
    expect(h.onEnd).toHaveBeenCalledTimes(1);
    expect(h.onError).not.toHaveBeenCalled();
  });

  test("silence is not a transcript", () => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    const h = handlers();
    startSpeechInput(h);

    FakeRecognition.last.hear("   ");

    expect(h.onTranscript).not.toHaveBeenCalled();
  });

  test.each([
    ["not-allowed", /Mikrofon/],
    ["no-speech", /nichts gehört/],
    ["network", /Spracheingabe/],
  ])("a %s error is explained in German", (code, message) => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    const h = handlers();
    startSpeechInput(h);

    FakeRecognition.last.onerror?.({ error: code });

    expect(h.onError).toHaveBeenCalledWith(expect.stringMatching(message));
  });

  test("stop lets the browser finish and still delivers what was heard", () => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    const h = handlers();
    const listening = startSpeechInput(h)!;

    listening.stop();
    FakeRecognition.last.hear("Milch");

    expect(FakeRecognition.last.stopped).toBe(true);
    expect(h.onTranscript).toHaveBeenCalledWith("Milch");
  });

  test("cancel drops whatever was heard and reports the end", () => {
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    const h = handlers();
    const listening = startSpeechInput(h)!;

    listening.cancel();
    FakeRecognition.last.hear("Milch");

    expect(FakeRecognition.last.aborted).toBe(true);
    expect(h.onTranscript).not.toHaveBeenCalled();
    expect(h.onError).not.toHaveBeenCalled();
    expect(h.onEnd).toHaveBeenCalled();
  });
});
