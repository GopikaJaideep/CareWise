import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Wind, X, Pause, Play } from "lucide-react";
import { usePageTitle } from "../lib/usePageTitle";

/*
 * "Take a breather": a short, calming activity for caregivers.
 *
 * Designed to relax without hooking anyone: no score, points, streaks, levels or rewards;
 * a fixed length chosen up front that ends by itself; a closing screen that points back to
 * real life rather than "play again"; and after two breathers in an hour the replay option
 * is withdrawn in favour of a suggestion to step away from the screen. No sound.
 */

const LENGTHS = [1, 3, 5]; // minutes
// Breathing pace: a longer out-breath than in-breath is the calming part.
const PHASES = [
  { label: "Breathe in", seconds: 4 },
  { label: "Hold", seconds: 2 },
  { label: "Breathe out", seconds: 6 },
] as const;
const CYCLE = PHASES.reduce((sum, p) => sum + p.seconds, 0);

const HISTORY_KEY = "carewise_breathers";
const HOUR_MS = 60 * 60 * 1000;
const MAX_PER_HOUR = 2;

function recentSessions(): number[] {
  try {
    const raw = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    const now = Date.now();
    return Array.isArray(raw) ? raw.filter((t) => typeof t === "number" && now - t < HOUR_MS) : [];
  } catch {
    return [];
  }
}

function recordSession() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify([...recentSessions(), Date.now()]));
  } catch {
    /* private mode etc. — the limit simply won't apply */
  }
}

/** Where we are in the breathing cycle: which phase, and how far through it (0-1). */
function breathAt(seconds: number) {
  let t = seconds % CYCLE;
  for (const phase of PHASES) {
    if (t < phase.seconds) return { phase, progress: t / phase.seconds };
    t -= phase.seconds;
  }
  return { phase: PHASES[0], progress: 0 };
}

/** Orb size, 0 (empty lungs) to 1 (full), eased so it feels like a breath, not a metronome. */
function orbFullness(seconds: number) {
  const { phase, progress } = breathAt(seconds);
  const ease = (x: number) => 0.5 - Math.cos(Math.PI * x) / 2;
  if (phase.label === "Breathe in") return ease(progress);
  if (phase.label === "Hold") return 1;
  return 1 - ease(progress);
}

type Stage = "choose" | "running" | "done";

export function BreathePage() {
  usePageTitle("Take a breather");
  const [stage, setStage] = useState<Stage>("choose");
  const [minutes, setMinutes] = useState(3);
  const [sessionsThisHour, setSessionsThisHour] = useState(() => recentSessions().length);

  const finish = () => {
    recordSession();
    setSessionsThisHour(recentSessions().length);
    setStage("done");
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex min-h-full max-w-2xl flex-col px-4 py-8 md:px-6">
        {stage === "choose" && (
          <ChooseScreen
            minutes={minutes}
            setMinutes={setMinutes}
            sessionsThisHour={sessionsThisHour}
            onStart={() => setStage("running")}
          />
        )}
        {stage === "running" && (
          <Pond minutes={minutes} onFinish={finish} onExit={() => setStage("choose")} />
        )}
        {stage === "done" && (
          <DoneScreen
            minutes={minutes}
            sessionsThisHour={sessionsThisHour}
            onAgain={() => setStage("choose")}
          />
        )}
      </div>
    </div>
  );
}

function ChooseScreen({
  minutes,
  setMinutes,
  sessionsThisHour,
  onStart,
}: {
  minutes: number;
  setMinutes: (m: number) => void;
  sessionsThisHour: number;
  onStart: () => void;
}) {
  return (
    <div className="my-auto text-center animate-fade-in">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-sage-50 text-sage-600">
        <Wind className="h-6 w-6" aria-hidden="true" />
      </div>
      <h1 className="mt-6 font-serif text-3xl font-semibold tracking-tight text-ink-900">Take a breather</h1>
      <p className="mx-auto mt-3 max-w-md text-ink-600">
        Follow the glowing circle: breathe in as it grows, out as it shrinks. Tap the water if you
        like. There's nothing to win. It ends on its own.
      </p>

      <fieldset className="mt-8">
        <legend className="text-sm font-medium text-ink-800">How long have you got?</legend>
        <div className="mt-3 flex justify-center gap-2">
          {LENGTHS.map((m) => (
            <label
              key={m}
              className={`cursor-pointer rounded-xl border px-5 py-3 text-sm font-medium transition-colors focus-within:ring-2 focus-within:ring-sage-400 ${
                minutes === m
                  ? "border-sage-500 bg-sage-50 text-sage-700"
                  : "border-sand-200 bg-white text-ink-700 hover:border-sage-300"
              }`}
            >
              <input
                type="radio"
                name="length"
                value={m}
                checked={minutes === m}
                onChange={() => setMinutes(m)}
                className="sr-only"
              />
              {m} min
            </label>
          ))}
        </div>
      </fieldset>

      {sessionsThisHour >= MAX_PER_HOUR && (
        <p className="mx-auto mt-6 max-w-sm rounded-lg bg-sand-100 p-3 text-sm text-ink-700">
          You've already had {sessionsThisHour} breathers this hour. A few minutes away from any screen
          might help even more: some water, a stretch, or a step outside.
        </p>
      )}

      <button onClick={onStart} className="btn-primary mt-8 px-6 py-3 text-base">
        Begin
      </button>
      <p className="mt-4 text-xs text-ink-600">No sound. You can stop at any time.</p>
    </div>
  );
}

function DoneScreen({
  minutes,
  sessionsThisHour,
  onAgain,
}: {
  minutes: number;
  sessionsThisHour: number;
  onAgain: () => void;
}) {
  const canGoAgain = sessionsThisHour < MAX_PER_HOUR;
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);

  return (
    <div className="my-auto text-center animate-fade-in">
      <h1 ref={headingRef} tabIndex={-1} className="font-serif text-3xl font-semibold tracking-tight text-ink-900 focus:outline-none">
        That's your {minutes} {minutes === 1 ? "minute" : "minutes"}.
      </h1>
      <p className="mx-auto mt-3 max-w-md text-ink-600">
        Before you jump back in, notice how your shoulders and jaw feel. If you can, have a glass of
        water on the way.
      </p>
      <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
        <Link to="/app" className="btn-primary">
          Back to home
        </Link>
        <Link to="/app/chat" className="btn-ghost">
          Talk something through
        </Link>
      </div>
      {canGoAgain ? (
        <button onClick={onAgain} className="mt-6 text-sm text-ink-600 underline underline-offset-4 hover:text-ink-900">
          I need another one
        </button>
      ) : (
        <p className="mx-auto mt-6 max-w-sm text-sm text-ink-600">
          That's {sessionsThisHour} breathers this hour. The rest of your break is best spent away from the screen.
        </p>
      )}
    </div>
  );
}

interface Ripple { x: number; y: number; born: number }
interface Petal { x: number; y: number; vx: number; vy: number; angle: number; spin: number; size: number }

function Pond({ minutes, onFinish, onExit }: { minutes: number; onFinish: () => void; onExit: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [paused, setPaused] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [phaseLabel, setPhaseLabel] = useState<string>(PHASES[0].label);
  const reducedMotion = useRef(
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  // Mutable animation state lives in refs so the draw loop doesn't re-render React every frame.
  const state = useRef({ elapsed: 0, last: 0, ripples: [] as Ripple[], petals: [] as Petal[], paused: false });
  const total = minutes * 60;

  useEffect(() => {
    state.current.paused = paused;
  }, [paused]);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let frame = 0;
    // Belt and braces alongside cancelAnimationFrame: once this screen is gone (or has finished),
    // no stray frame may draw or record another finished breather.
    let stopped = false;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (state.current.petals.length === 0) {
        state.current.petals = Array.from({ length: 6 }, () => ({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 6,
          vy: (Math.random() - 0.5) * 6,
          angle: Math.random() * Math.PI * 2,
          spin: (Math.random() - 0.5) * 0.2,
          size: 7 + Math.random() * 5,
        }));
      }
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = (now: number) => {
      if (stopped) return;
      const s = state.current;
      const gap = s.last ? (now - s.last) / 1000 : 0;
      s.last = now;
      // The clock follows real time even when frames are slow (a busy phone), but a gap over a
      // second means the tab was hidden, and a hidden breather counts as paused.
      if (!s.paused && gap < 1) s.elapsed += gap;
      // Physics takes small steps only, so a slow frame can't fling the petals.
      const dt = Math.min(gap, 0.1);

      if (s.elapsed >= total) {
        stopped = true;
        onFinish();
        return;
      }

      const { width: w, height: h } = canvas.getBoundingClientRect();
      // Water
      const water = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
      water.addColorStop(0, "#F1F4F0");
      water.addColorStop(1, "#DDE6DA");
      ctx.fillStyle = water;
      ctx.fillRect(0, 0, w, h);

      // Breathing orb
      const fullness = reducedMotion.current ? 0.6 : orbFullness(s.elapsed);
      const base = Math.min(w, h) * 0.14;
      const radius = base + fullness * base * 0.9;
      const glow = ctx.createRadialGradient(w / 2, h / 2, radius * 0.2, w / 2, h / 2, radius * 1.6);
      glow.addColorStop(0, "rgba(144, 178, 140, 0.55)");
      glow.addColorStop(1, "rgba(144, 178, 140, 0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(w / 2, h / 2, radius * 1.6, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "rgba(250, 247, 242, 0.9)";
      ctx.beginPath();
      ctx.arc(w / 2, h / 2, radius, 0, Math.PI * 2);
      ctx.fill();

      // Ripples: expand and fade over 3.5 s
      s.ripples = s.ripples.filter((r) => s.elapsed - r.born < 3.5);
      for (const r of s.ripples) {
        const age = (s.elapsed - r.born) / 3.5;
        for (const offset of [0, 0.18]) {
          const a = Math.max(0, age - offset);
          if (a <= 0) continue;
          ctx.strokeStyle = `rgba(79, 122, 78, ${0.35 * (1 - a)})`;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(r.x, r.y, 6 + a * 120, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // Petals drift, pushed gently by nearby ripples, and wrap around the edges
      for (const p of s.petals) {
        if (!s.paused && !reducedMotion.current) {
          for (const r of s.ripples) {
            const dx = p.x - r.x;
            const dy = p.y - r.y;
            const dist = Math.hypot(dx, dy) || 1;
            const front = 6 + ((s.elapsed - r.born) / 3.5) * 120;
            if (Math.abs(dist - front) < 12) {
              p.vx += (dx / dist) * 0.8;
              p.vy += (dy / dist) * 0.8;
            }
          }
          p.vx *= 0.985;
          p.vy *= 0.985;
          p.x = (p.x + p.vx * dt + w) % w;
          p.y = (p.y + p.vy * dt + h) % h;
          p.angle += p.spin * dt;
        }
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.angle);
        ctx.fillStyle = "rgba(229, 194, 176, 0.85)";
        ctx.beginPath();
        ctx.ellipse(0, 0, p.size, p.size * 0.55, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }

      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    // Update the on-screen text a few times a second, not every frame.
    const ticker = window.setInterval(() => {
      const s = state.current;
      setElapsed(Math.floor(s.elapsed));
      setPhaseLabel(breathAt(s.elapsed).phase.label);
    }, 250);

    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      window.clearInterval(ticker);
      window.removeEventListener("resize", resize);
    };
    // onFinish is stable for the life of this screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [total]);

  const addRipple = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (paused) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const s = state.current;
    s.ripples.push({ x: e.clientX - rect.left, y: e.clientY - rect.top, born: s.elapsed });
    if (s.ripples.length > 12) s.ripples.shift();
  };

  const remaining = Math.max(0, total - elapsed);
  const mm = Math.floor(remaining / 60);
  const ss = String(remaining % 60).padStart(2, "0");

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex items-center justify-between">
        <span className="text-sm tabular-nums text-ink-600" aria-label={`${mm} minutes ${ss} seconds left`}>
          {mm}:{ss} left
        </span>
        <div className="flex gap-1">
          <button
            onClick={() => setPaused((p) => !p)}
            className="btn-ghost"
            aria-label={paused ? "Resume" : "Pause"}
          >
            {paused ? <Play className="h-4 w-4" aria-hidden="true" /> : <Pause className="h-4 w-4" aria-hidden="true" />}
            <span className="hidden sm:inline">{paused ? "Resume" : "Pause"}</span>
          </button>
          <button onClick={onExit} className="btn-ghost" aria-label="Stop">
            <X className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">Stop</span>
          </button>
        </div>
      </div>

      <div className="relative mt-4 min-h-[320px] flex-1 overflow-hidden rounded-3xl border border-sage-200 shadow-soft">
        <canvas
          ref={canvasRef}
          onPointerDown={addRipple}
          className="absolute inset-0 h-full w-full touch-none"
          aria-hidden="true"
        />
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <p className="font-serif text-2xl text-sage-700">{paused ? "Paused" : phaseLabel}</p>
        </div>
      </div>

      <p className="sr-only" role="status">
        Breathing guide running for {minutes} {minutes === 1 ? "minute" : "minutes"}: breathe in for 4 seconds, hold for 2, and out for 6.
      </p>
      <p className="mt-3 text-center text-xs text-ink-600">
        In for 4, hold for 2, out for 6. Tap the water whenever you like.
      </p>
    </div>
  );
}
