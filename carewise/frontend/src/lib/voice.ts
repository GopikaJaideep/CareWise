/**
 * Carrie's voice: replies read aloud with the browser's own speech synthesis (Web Speech API).
 * Nothing leaves the device and there's no cost. Off until the person turns it on.
 *
 * Carrie sounds childlike: browsers have no child voices, so a light voice is pitched well up and
 * spoken gently. Lighter (usually female-labelled) voices are preferred because a deep voice pitched
 * up sounds strained rather than young. Natural-sounding voices come first, then Australian, then
 * British English. Crisis replies are read in a calm, normal voice instead, because a childlike
 * voice is wrong there.
 */
import { useEffect, useState } from "react";

export const voiceSupported =
  typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

let cachedVoice: SpeechSynthesisVoice | null | undefined;

function pickVoice(): SpeechSynthesisVoice | null {
  if (cachedVoice !== undefined) return cachedVoice;
  const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("en"));
  if (voices.length === 0) return null; // not loaded yet; try again next time
  const score = (v: SpeechSynthesisVoice) =>
    (/natural|neural|online|premium|enhanced/i.test(v.name) ? 4 : 0) +
    (/en[-_]au/i.test(v.lang) ? 3 : /en[-_]gb/i.test(v.lang) ? 2 : 0) +
    (/aria|jenny|ana|natasha|sonia|libby|maisie|zira|hazel|susan|samantha|karen|moira|tessa|female/i.test(v.name) ? 2 : 0) -
    (/david|mark|guy|william|ryan|daniel|george|james|richard|\bmale\b/i.test(v.name) ? 1 : 0);
  cachedVoice = [...voices].sort((a, b) => score(b) - score(a))[0];
  return cachedVoice;
}

if (voiceSupported) {
  // Voices load asynchronously in most browsers; pick again once they arrive.
  window.speechSynthesis.addEventListener?.("voiceschanged", () => {
    cachedVoice = undefined;
  });
}

/** Make a chat reply sound natural when spoken: no markdown, links or "6/10". */
export function textForSpeech(text: string): string {
  return text
    .replace(/\*\*/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\((\s*)\)/g, "")
    .replace(/(\d+)\s*\/\s*10\b/g, "$1 out of 10")
    .replace(/[•·]/g, ",")
    .replace(/\n+/g, ". ")
    .replace(/\s*\.\s*(\.\s*)+/g, ". ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Short pieces, because some browsers stop a single long utterance part-way through. */
export function speechChunks(text: string): string[] {
  return (text.match(/[^.!?]+[.!?]*/g) ?? [])
    .map((s) => s.trim())
    .filter((s) => /[a-z0-9]/i.test(s));
}

// Whether Carrie is speaking right now, so his mouth can move while he talks.
let speaking = false;
const listeners = new Set<(on: boolean) => void>();
function setSpeaking(on: boolean) {
  speaking = on;
  listeners.forEach((l) => l(on));
}

export function useCarrieSpeaking(): boolean {
  const [on, setOn] = useState(speaking);
  useEffect(() => {
    listeners.add(setOn);
    return () => {
      listeners.delete(setOn);
    };
  }, []);
  return on;
}

// Each reading gets a number, so events from a cancelled reading (which can arrive late) are ignored.
let reading = 0;

export function stopSpeaking() {
  if (!voiceSupported) return;
  reading++;
  window.speechSynthesis.cancel();
  setSpeaking(false);
}

export function speakAsCarrie(text: string, { calm = false }: { calm?: boolean } = {}) {
  if (!voiceSupported) return;
  stopSpeaking();
  const chunks = speechChunks(textForSpeech(text));
  if (chunks.length === 0) return;
  const voice = pickVoice();
  const mine = reading;
  const done = () => {
    if (mine === reading) setSpeaking(false);
  };
  chunks.forEach((chunk, i) => {
    const u = new SpeechSynthesisUtterance(chunk);
    if (voice) u.voice = voice;
    u.lang = voice?.lang ?? "en-AU";
    u.rate = calm ? 0.9 : 0.95;
    u.pitch = calm ? 1 : 1.75; // 2 is the maximum; much higher sounds squeaky
    u.volume = 0.9;
    if (i === 0) u.onstart = () => mine === reading && setSpeaking(true);
    if (i === chunks.length - 1) u.onend = done;
    u.onerror = done;
    window.speechSynthesis.speak(u);
  });
}
