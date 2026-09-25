import { useId } from "react";
import { usePreference } from "../lib/preference";

/** The buddy's name, used in the chat's greeting and the show/hide control. */
export const BUDDY_NAME = "Carrie";

/**
 * What Carrie is doing. Kept deliberately small and gentle: this is a companion for people under
 * strain, so there is no excitement, no rewards and nothing to chase.
 *
 * - idle: blinks now and then, an ear twitches, the gem glows softly
 * - listening: the person is typing; ears lift, pupils widen
 * - thinking: waiting for the reply; eyes look up
 * - talking: the reply is streaming in
 * - caring: after emotional support, a symptom or a check-in; soft eyes, a small heart
 * - glad: after something practical got done (a task, an answer); a small smile
 * - steady: a crisis reply; calm, open eyes, no blush and no movement except blinking
 */
export type BuddyMood = "idle" | "listening" | "thinking" | "talking" | "caring" | "glad" | "steady";

/** How Carrie responds to a reply from these agents. */
export function moodForReply(agents: string[] | undefined): BuddyMood {
  if (!agents || agents.length === 0) return "idle";
  if (agents.includes("safety")) return "steady";
  if (agents.some((a) => a === "emotional_support" || a === "burnout_monitor" || a === "symptom_tracker")) return "caring";
  return "glad";
}

// Colours (SVG attributes can't take Tailwind classes). Greens and sands are from tailwind.config.js.
const C = {
  fur: "#2F4A30", // sage-700
  furLight: "#4F7A4E", // sage-500, the soft glow in the middle of the face
  earInner: "#C4AE89", // sand-400
  speckle: "#BACFB6", // sage-200
  leafA: "#6A9468", // sage-400
  leafB: "#90B28C", // sage-300
  gem: "#5FB8A8",
  gemLight: "#A8E4D9",
  iris: "#C27A30",
  irisEdge: "#8A5A22",
  pupil: "#1F1B16", // ink-900
  ink: "#1F1B16",
  whisker: "#DDE6DA", // sage-100
  blush: "#D29A82", // clay-300
  heart: "#D29A82",
};

/** An almond-shaped leaf pointing down, centred on (x, y): the leafy ruff on Carrie's chest. */
function leaf(x: number, y: number) {
  return `M${x} ${y - 3.6} C${x + 2.3} ${y - 1.6} ${x + 2.3} ${y + 1.6} ${x} ${y + 3.6} C${x - 2.3} ${y + 1.6} ${x - 2.3} ${y - 1.6} ${x} ${y - 3.6} Z`;
}

interface BuddyProps {
  mood?: BuddyMood;
  size?: number;
  /** A still picture: no blinking or twitching (used for the avatar beside every past message). */
  still?: boolean;
  className?: string;
}

/**
 * Carrie: a small forest cat-spirit who helps carry the load. Drawn in SVG so he stays crisp at
 * any size and can change expression. Decorative only (aria-hidden); the chat announces its own state.
 */
export function Buddy({ mood = "idle", size = 40, still = false, className = "" }: BuddyProps) {
  const glowId = `carrie-glow-${useId().replace(/:/g, "")}`;
  const animate = !still && mood !== "steady";
  const softEyes = mood === "caring" || mood === "glad";
  const blush = softEyes ? 0.55 : mood === "steady" ? 0 : 0.25;
  const pupil = mood === "listening" ? 3.4 : 2.8;
  const look = mood === "thinking" ? { x: 0.9, y: -1.4 } : { x: 0, y: 0 };

  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 overflow-visible ${className}`}
    >
      <defs>
        <radialGradient id={glowId} cx="50%" cy="58%" r="55%">
          <stop offset="0%" stopColor={C.furLight} />
          <stop offset="100%" stopColor={C.fur} />
        </radialGradient>
      </defs>
      <ellipse cx="32" cy="60" rx="15" ry="2.4" fill={C.ink} opacity="0.1" />

      {/* key: restarts the one-off "settle" movement whenever the mood changes */}
      <g key={mood} className={animate ? (mood === "glad" ? "buddy-hop" : "buddy-breathe") : undefined}>
        {/* Ears. Outer group lifts them when listening; inner group carries the idle twitch. */}
        <g style={{ transformOrigin: "20px 24px", transform: mood === "listening" ? "rotate(-6deg) translateY(-1px)" : "none", transition: "transform 300ms ease-out" }}>
          <path d="M13.5 27 C10.5 17 11.5 9.5 14.5 6 C20 9 25 14 27.5 20.5 Z" fill={C.fur} />
          <path d="M15.8 23.5 C14.3 16.5 14.8 11.5 16.3 9.2 C19.6 11.6 22.6 15.2 24.2 19.6 Z" fill={C.earInner} />
          <circle cx="17.2" cy="13.5" r="0.7" fill={C.speckle} opacity="0.8" />
          <circle cx="19.4" cy="16.6" r="0.55" fill={C.speckle} opacity="0.8" />
        </g>
        <g style={{ transformOrigin: "44px 24px", transform: mood === "listening" ? "rotate(6deg) translateY(-1px)" : "none", transition: "transform 300ms ease-out" }}>
          <g className={animate ? "buddy-twitch" : undefined}>
            <path d="M50.5 27 C53.5 17 52.5 9.5 49.5 6 C44 9 39 14 36.5 20.5 Z" fill={C.fur} />
            <path d="M48.2 23.5 C49.7 16.5 49.2 11.5 47.7 9.2 C44.4 11.6 41.4 15.2 39.8 19.6 Z" fill={C.earInner} />
            <circle cx="46.8" cy="13.5" r="0.7" fill={C.speckle} opacity="0.8" />
            <circle cx="44.6" cy="16.6" r="0.55" fill={C.speckle} opacity="0.8" />
          </g>
        </g>

        {/* Fluffy cheek tufts and a tuft on top, behind the head. */}
        <path d="M11 37.5 L6.3 40.2 L10.2 41.8 L6.6 44.8 L11.8 45.6 Z" fill={C.fur} />
        <path d="M53 37.5 L57.7 40.2 L53.8 41.8 L57.4 44.8 L52.2 45.6 Z" fill={C.fur} />
        <path d="M29 17.6 Q30.6 13 32.4 16.6 Q34 13.4 35.4 17.6 Z" fill={C.fur} />

        {/* Head and body in one soft shape, lighter in the middle. */}
        <path
          d="M32 16.5 C46.5 16.5 55 26 55 37.5 C55 49.5 45 56.5 32 56.5 C19 56.5 9 49.5 9 37.5 C9 26 17.5 16.5 32 16.5 Z"
          fill={`url(#${glowId})`}
        />

        {/* Leafy chest ruff. */}
        <g>
          <path d={leaf(26.8, 52.6)} fill={C.leafA} />
          <path d={leaf(37.2, 52.6)} fill={C.leafA} />
          <path d={leaf(32, 53.6)} fill={C.leafB} />
          <path d={leaf(29.3, 56)} fill={C.leafB} opacity="0.9" />
          <path d={leaf(34.7, 56)} fill={C.leafA} opacity="0.9" />
        </g>

        {/* Forehead gem, with two small ones beside it. */}
        <g className={animate ? "buddy-glow" : undefined}>
          <path d="M32 19.5 L35.2 23.8 L32 28 L28.8 23.8 Z" fill={C.gem} />
          <path d="M32 19.5 L35.2 23.8 L28.8 23.8 Z" fill={C.gemLight} />
          <path d="M23.6 22.2 L24.8 23.6 L23.6 25 L22.4 23.6 Z" fill={C.gemLight} opacity="0.85" />
          <path d="M40.4 22.2 L41.6 23.6 L40.4 25 L39.2 23.6 Z" fill={C.gemLight} opacity="0.85" />
          <circle cx="27.6" cy="28.4" r="0.5" fill={C.speckle} opacity="0.8" />
          <circle cx="36.4" cy="28.4" r="0.5" fill={C.speckle} opacity="0.8" />
          <circle cx="32" cy="30.2" r="0.45" fill={C.speckle} opacity="0.7" />
        </g>

        {/* Eyes: big and amber; soft closed arcs when caring or glad. */}
        {softEyes ? (
          <g stroke={C.iris} strokeWidth="2.2" strokeLinecap="round" fill="none">
            <path d="M18.8 37.5 Q23.5 32.8 28.2 37.5" />
            <path d="M35.8 37.5 Q40.5 32.8 45.2 37.5" />
          </g>
        ) : (
          <g className={!still ? "buddy-blink" : undefined}>
            {[23.5, 40.5].map((cx) => (
              <g key={cx}>
                <circle cx={cx} cy="36.5" r="5.7" fill={C.iris} stroke={C.irisEdge} strokeWidth="0.9" />
                <circle
                  cx={cx + look.x}
                  cy={36.5 + look.y}
                  r={pupil}
                  fill={C.pupil}
                  style={{ transition: "r 250ms ease-out, cx 300ms ease-out, cy 300ms ease-out" }}
                />
                <circle cx={cx - 1.9 + look.x} cy={34.5 + look.y} r="1.4" fill="#FFFFFF" />
                <circle cx={cx + 1.7 + look.x} cy={38.3 + look.y} r="0.6" fill="#FFFFFF" opacity="0.7" />
              </g>
            ))}
          </g>
        )}

        {/* Cheeks. */}
        <ellipse cx="17.5" cy="43" rx="3" ry="1.7" fill={C.blush} opacity={blush} />
        <ellipse cx="46.5" cy="43" rx="3" ry="1.7" fill={C.blush} opacity={blush} />

        {/* Whiskers. */}
        <g stroke={C.whisker} strokeWidth="0.6" strokeLinecap="round" opacity="0.75">
          <path d="M22 43.5 L11.5 41.5" />
          <path d="M22 45 L11.5 46" />
          <path d="M42 43.5 L52.5 41.5" />
          <path d="M42 45 L52.5 46" />
        </g>

        {/* Nose and mouth. */}
        <path d="M30.3 42.4 L33.7 42.4 L32 44.4 Z" fill={C.ink} stroke={C.ink} strokeWidth="0.8" strokeLinejoin="round" />
        {mood === "talking" ? (
          <ellipse cx="32" cy="47.2" rx="1.9" ry="1.6" fill={C.ink} className={animate ? "buddy-talk" : undefined} />
        ) : mood === "glad" ? (
          <path d="M28 45.6 Q32 50 36 45.6" stroke={C.ink} strokeWidth="1.3" strokeLinecap="round" fill="none" />
        ) : mood === "thinking" || mood === "steady" ? (
          <path d="M30 46.6 Q32 47.3 34 46.6" stroke={C.ink} strokeWidth="1.3" strokeLinecap="round" fill="none" />
        ) : (
          <g stroke={C.ink} strokeWidth="1.3" strokeLinecap="round" fill="none">
            <path d="M32 44.4 Q31 47 28.6 46.2" />
            <path d="M32 44.4 Q33 47 35.4 46.2" />
          </g>
        )}
      </g>

      {mood === "caring" && animate && (
        <path
          className="buddy-heart"
          d="M50 18 C50 16.3 52.2 15.6 53 17.1 C53.8 15.6 56 16.3 56 18 C56 20 53 21.8 53 21.8 C53 21.8 50 20 50 18 Z"
          fill={C.heart}
        />
      )}
    </svg>
  );
}

/** Whether to show Carrie. On by default; remembered in this browser only. */
export function useBuddyEnabled(): [boolean, (enabled: boolean) => void] {
  return usePreference("carewise.buddy", true);
}
