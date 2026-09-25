/**
 * Voice messages: speak instead of typing. Uses the browser's speech recognition (Web Speech API),
 * which writes what the person says into the message box as they talk. Nothing is sent until they
 * press send, so they can check it first: a misheard word could change a symptom or a date.
 *
 * Privacy: in Chrome and Edge, speech recognition runs on the browser maker's online service
 * (Google or Microsoft), not on CareWise's server. The mic button says so on first use.
 *
 * Supported in Chrome, Edge and Safari; the mic button is hidden where it isn't (e.g. Firefox).
 */
import { useEffect, useRef, useState } from "react";

// Minimal types: TypeScript's DOM library doesn't include the prefixed constructor.
interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}
interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

const Ctor: RecognitionCtor | undefined =
  typeof window === "undefined"
    ? undefined
    : (window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor })
        .SpeechRecognition ??
      (window as unknown as { webkitSpeechRecognition?: RecognitionCtor }).webkitSpeechRecognition;

export const dictationSupported = Boolean(Ctor);

/** Join what was already typed with what's being said, with one space between. */
export function joinSpoken(before: string, spoken: string): string {
  const said = spoken.replace(/\s+/g, " ").trim();
  if (!said) return before;
  return before.trim() ? `${before.replace(/\s+$/, "")} ${said}` : said.charAt(0).toUpperCase() + said.slice(1);
}

const ERRORS: Record<string, string> = {
  "not-allowed": "Microphone access is blocked. You can allow it in your browser's site settings, or type instead.",
  "service-not-allowed": "Voice input isn't available in this browser. You can type instead.",
  "audio-capture": "No microphone was found. You can type instead.",
  network: "Voice input needs an internet connection. You can type instead.",
};

/**
 * Dictate into a text box. `text` is the box's current value and `setText` updates it; spoken words
 * are added after whatever was already typed.
 */
export function useDictation(text: string, setText: (value: string) => void) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<Recognition | null>(null);
  const setTextRef = useRef(setText);
  setTextRef.current = setText;

  useEffect(() => () => recognitionRef.current?.abort(), []);

  const start = () => {
    if (!Ctor || recognitionRef.current) return;
    setError(null);
    const before = text;
    const recognition = new Ctor();
    recognition.lang = navigator.language || "en-AU";
    recognition.continuous = true; // keep listening through pauses until they stop it
    recognition.interimResults = true; // show words as they're said
    recognition.onresult = (e) => {
      let spoken = "";
      for (let i = 0; i < e.results.length; i++) spoken += e.results[i][0].transcript;
      setTextRef.current(joinSpoken(before, spoken));
    };
    recognition.onerror = (e) => {
      // "no-speech" and "aborted" just end the recording quietly.
      if (ERRORS[e.error]) setError(ERRORS[e.error]);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setRecording(false);
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
      setRecording(true);
    } catch {
      recognitionRef.current = null;
      setError("Couldn't start voice input. Please try again, or type instead.");
    }
  };

  /** Stop listening; words already heard stay in the box. */
  const stop = () => recognitionRef.current?.stop();

  /** Stop at once and ignore anything still being processed (used when the message is sent). */
  const cancel = () => {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    recognition.onresult = null;
    recognition.abort();
  };

  return { recording, error, start, stop, cancel };
}
