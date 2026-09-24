import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine,
} from "recharts";
import {
  Activity, Calendar, Battery, Pill, ArrowRight, Loader2, MessageCircle,
  BellRing, BellOff, Sparkles, RefreshCw, Wind,
} from "lucide-react";
import { api, type DashboardSummary } from "../lib/api";
import { useAuth } from "../lib/auth";
import { disablePushReminders, enablePushReminders, pushPermission } from "../lib/push";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { usePageTitle } from "../lib/usePageTitle";
import { MemoryCard } from "../components/MemoryCard";

const STARTERS = [
  "Mum had nausea this morning, around a 6.",
  "Add: oncology appointment Tuesday at 10am.",
  "I'm exhausted. Don't know how to keep going.",
  "I'd like to do a burnout check-in.",
];

export function DashboardPage() {
  usePageTitle("Home");
  const { user } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [showCheckin, setShowCheckin] = useState(false);
  const [checkinResult, setCheckinResult] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setFailed(false);
    api
      .dashboard()
      .then(setSummary)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleCheckinSaved = async (score: number, category: string) => {
    setShowCheckin(false);
    setCheckinResult(`Saved. Today's score is ${Math.round(score)} out of 100 (${category}).`);
    // Refresh quietly so the score and trend update without a full-page spinner.
    try {
      setSummary(await api.dashboard());
    } catch {
      /* the saved check-in shows on the next load */
    }
  };

  if (loading) {
    return (
      <div role="status" className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-ink-500" aria-hidden="true" />
        <span className="sr-only">Loading your dashboard…</span>
      </div>
    );
  }
  if (failed || !summary) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div role="alert" className="max-w-sm text-center">
          <h1 className="font-serif text-2xl font-semibold text-ink-900">We couldn't load your dashboard</h1>
          <p className="mt-2 text-sm text-ink-600">
            Your information is safe. This is usually a connection hiccup.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <button onClick={load} className="btn-primary">
              <RefreshCw className="h-4 w-4" aria-hidden="true" /> Try again
            </button>
            <Link to="/app/chat" className="btn-ghost">Go to chat</Link>
          </div>
        </div>
      </div>
    );
  }

  const isNewUser =
    summary.recent_symptom_count === 0 &&
    summary.open_tasks_count === 0 &&
    summary.active_medications === 0 &&
    summary.latest_burnout_score === null;

  const greeting = getGreeting();
  const trendData = summary.burnout_trend.map((score, i) => ({
    name: `#${i + 1}`,
    score,
  }));

  const burnoutColor =
    summary.burnout_category === "very high"
      ? "text-red-600"
      : summary.burnout_category === "high"
      ? "text-clay-500"
      : summary.burnout_category === "moderate"
      ? "text-clay-400"
      : "text-sage-600";

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-8 md:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm text-ink-600">{greeting}</p>
            <h1 className="mt-1 font-serif text-3xl font-semibold tracking-tight text-ink-900">
              {user?.display_name ? `Hi, ${user.display_name}` : "Hi"}
            </h1>
          </div>
          {!isNewUser && (
            <Link to="/app/chat" className="btn-primary">
              <MessageCircle className="h-4 w-4" aria-hidden="true" />
              Talk to CareWise
            </Link>
          )}
        </div>

        {isNewUser && (
          <section className="card mt-6 border-sage-200" aria-labelledby="start-heading">
            <h2 id="start-heading" className="font-serif text-xl font-semibold text-ink-900">
              Start here: tell CareWise what's going on
            </h2>
            <p className="mt-1 text-sm text-ink-600">
              Just type like you'd text a friend. CareWise files symptoms, appointments and meds for
              you. Tap an example to try it:
            </p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {STARTERS.map((s) => (
                <Link
                  key={s}
                  to="/app/chat"
                  state={{ initialPrompt: s }}
                  className="rounded-lg border border-sand-200 bg-sand-50 p-3 text-sm text-ink-800 transition-colors hover:border-sage-300 hover:bg-white"
                >
                  "{s}"
                </Link>
              ))}
            </div>
            <Link to="/app/chat" className="btn-primary mt-5 w-full sm:w-auto">
              <MessageCircle className="h-4 w-4" aria-hidden="true" />
              Or write your own message
            </Link>
          </section>
        )}

        <div className="mt-6 flex items-start gap-3 rounded-xl border border-sage-200 bg-sage-50 p-4">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-sage-600" aria-hidden="true" />
          <p className="text-sm italic text-ink-800">"{summary.quote_of_the_day}"</p>
        </div>

        <ReminderToggle />

        <div className="mt-8 grid gap-3 sm:grid-cols-3 sm:gap-4">
          <StatCard
            label="Open tasks"
            value={summary.open_tasks_count}
            sublabel={`${summary.today_tasks_count} due today`}
            Icon={Calendar}
            href="/app/tasks"
          />
          <StatCard
            label="Symptoms logged this week"
            value={summary.recent_symptom_count}
            sublabel={summary.recent_symptom_count === 0 ? "Nothing logged yet" : "Last 7 days"}
            Icon={Activity}
            href="/app/symptoms"
          />
          <StatCard
            label="Active medications"
            value={summary.active_medications}
            sublabel="Tracked in CareWise"
            Icon={Pill}
            href="/app/symptoms"
          />
        </div>

        {/* Burnout */}
        <div className="card mt-6">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sage-50 text-sage-600">
                <Battery className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <h2 className="font-serif text-xl font-semibold text-ink-900">Your wellbeing</h2>
                <p className="text-sm text-ink-600">How you've been doing, from your check-ins</p>
              </div>
            </div>
            {summary.latest_burnout_score !== null ? (
              <div className="animate-count-up text-right">
                <div className={`font-serif text-3xl font-semibold tabular-nums ${burnoutColor}`}>
                  <AnimatedNumber value={Math.round(summary.latest_burnout_score)} />
                </div>
                <div className="text-xs text-ink-600">/ 100 — {summary.burnout_category}</div>
              </div>
            ) : null}
          </div>

          {trendData.length > 1 ? (
            <div className="mt-6 h-32" role="img" aria-label={`Burnout scores from your last ${trendData.length} check-ins, most recent ${Math.round(summary.latest_burnout_score ?? 0)} out of 100`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <XAxis dataKey="name" stroke="#716A62" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 100]} stroke="#716A62" fontSize={11} tickLine={false} axisLine={false} />
                  <ReferenceLine y={55} stroke="#D29A82" strokeDasharray="3 3" label={{ value: "high", fontSize: 10, fill: "#965340" }} />
                  <ReferenceLine y={75} stroke="#B8755A" strokeDasharray="3 3" />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 8,
                      border: "1px solid #E8DFCE",
                      boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
                      fontSize: 12,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="score"
                    stroke="#4F7A4E"
                    strokeWidth={2}
                    dot={{ fill: "#4F7A4E", r: 3 }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : trendData.length === 1 ? (
            <p className="mt-6 text-sm text-ink-600">
              One check-in so far. Run another to start seeing your trend.
            </p>
          ) : (
            <p className="mt-6 text-sm text-ink-600">
              No check-ins yet. It takes 30 seconds: a few questions about your sleep, stress and energy.
            </p>
          )}

          {checkinResult && !showCheckin && (
            <p role="status" className="mt-4 rounded-lg bg-sage-50 p-3 text-sm text-sage-700">
              {checkinResult}
            </p>
          )}

          {showCheckin ? (
            <BurnoutCheckinForm onSaved={handleCheckinSaved} onCancel={() => setShowCheckin(false)} />
          ) : (
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <button
                onClick={() => {
                  setCheckinResult(null);
                  setShowCheckin(true);
                }}
                className="btn-primary"
              >
                <Battery className="h-4 w-4" aria-hidden="true" />
                {summary.latest_burnout_score === null ? "Do a check-in" : "New check-in"}
              </button>
              <Link
                to="/app/chat"
                state={{ initialPrompt: "I'd like to do a burnout check-in." }}
                className="btn-ghost"
              >
                Or talk it through in chat <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </div>
          )}

          <Link
            to="/app/breathe"
            className="mt-4 flex items-center gap-3 rounded-lg border border-sand-200 bg-sand-50 p-3 text-sm text-ink-800 transition-colors hover:border-sage-300 hover:bg-white"
          >
            <Wind className="h-4 w-4 shrink-0 text-sage-600" aria-hidden="true" />
            <span className="flex-1">
              <span className="font-medium">Take a breather.</span>{" "}
              <span className="text-ink-600">A calm 1–5 minute breathing pause. No score, it just ends.</span>
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-ink-500" aria-hidden="true" />
          </Link>

          {summary.burnout_category &&
            ["high", "very high"].includes(summary.burnout_category) && (
              <div className="mt-5 rounded-lg bg-clay-50 border border-clay-200 p-3 text-sm text-ink-800">
                <strong className="text-clay-500">A note:</strong> Your recent check-ins show you're
                running close to empty. Carer Gateway (1800 422 737) can arrange free respite — even a
                few hours. Cancer Council 13 11 20 also has free counselling for caregivers.
              </div>
            )}
        </div>

        <MemoryCard />
      </div>
    </div>
  );
}

function BurnoutCheckinForm({
  onSaved,
  onCancel,
}: {
  onSaved: (score: number, category: string) => void;
  onCancel: () => void;
}) {
  const [sleepHours, setSleepHours] = useState("");
  const [stress, setStress] = useState(5);
  const [energy, setEnergy] = useState(5);
  const [selfCareMinutes, setSelfCareMinutes] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.createBurnoutCheckin({
        sleep_hours: Number(sleepHours),
        stress_level: stress,
        energy_level: energy,
        self_care_minutes: Number(selfCareMinutes),
        notes: notes.trim() || undefined,
      });
      onSaved(res.burnout_score, res.category);
    } catch {
      setError("Couldn't save your check-in. Please check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Burnout check-in"
      className="mt-5 animate-slide-up space-y-4 rounded-xl border border-sand-200 bg-sand-50 p-4"
    >
      <p className="text-sm text-ink-700">Four quick questions about today. There are no wrong answers.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="checkin-sleep" className="mb-1 block text-xs font-medium text-ink-600">
            Hours of sleep last night
          </label>
          <input
            id="checkin-sleep"
            autoFocus
            required
            type="number"
            inputMode="decimal"
            min={0}
            max={24}
            step={0.5}
            className="input-field"
            placeholder="e.g. 6"
            value={sleepHours}
            onChange={(e) => setSleepHours(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="checkin-selfcare" className="mb-1 block text-xs font-medium text-ink-600">
            Minutes spent just on you today
          </label>
          <input
            id="checkin-selfcare"
            required
            type="number"
            inputMode="numeric"
            min={0}
            max={1440}
            step={1}
            className="input-field"
            placeholder="e.g. 15 (0 is fine)"
            value={selfCareMinutes}
            onChange={(e) => setSelfCareMinutes(e.target.value)}
          />
        </div>
      </div>
      <ScaleInput id="checkin-stress" label="Stress today" low="calm" high="overwhelmed" value={stress} onChange={setStress} />
      <ScaleInput id="checkin-energy" label="Energy today" low="exhausted" high="full of energy" value={energy} onChange={setEnergy} />
      <div>
        <label htmlFor="checkin-notes" className="mb-1 block text-xs font-medium text-ink-600">
          Anything else? <span className="font-normal">(optional)</span>
        </label>
        <input
          id="checkin-notes"
          type="text"
          maxLength={1000}
          className="input-field"
          placeholder="e.g. rough night at the hospital"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-clay-500">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="btn-ghost">
          Cancel
        </button>
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Saving…" /> : "Save check-in"}
        </button>
      </div>
    </form>
  );
}

function ScaleInput({
  id,
  label,
  low,
  high,
  value,
  onChange,
}: {
  id: string;
  label: string;
  low: string;
  high: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-xs font-medium text-ink-600">
        {label}: <span className="text-ink-900">{value}/10</span>
      </label>
      <input
        id={id}
        type="range"
        min={1}
        max={10}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={`${value} out of 10`}
        className="mt-1 w-full accent-sage-600"
      />
      <div className="flex justify-between text-xs text-ink-600" aria-hidden="true">
        <span>1 · {low}</span>
        <span>10 · {high}</span>
      </div>
    </div>
  );
}

function ReminderToggle() {
  const [status, setStatus] = useState<"loading" | "unsupported" | "off" | "on" | "denied">(
    "loading"
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const perm = pushPermission();
    if (perm === "unsupported") setStatus("unsupported");
    else if (perm === "denied") setStatus("denied");
    else if (perm === "granted") setStatus("on");
    else setStatus("off");
  }, []);

  if (status === "loading" || status === "unsupported") return null;

  const handleEnable = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await enablePushReminders();
      setStatus(result.ok ? "on" : result.reason === "denied" ? "denied" : "off");
      if (!result.ok && result.reason === "no_server_key") {
        setError("Reminders aren't set up on this server yet.");
      }
    } catch {
      setError("Couldn't turn on reminders. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const handleDisable = async () => {
    setBusy(true);
    setError(null);
    try {
      await disablePushReminders();
      setStatus("off");
    } catch {
      setError("Couldn't turn off reminders. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-sand-200 bg-white p-3.5 shadow-soft">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {status === "on" ? (
          <BellRing className="h-4 w-4 shrink-0 text-sage-600" aria-hidden="true" />
        ) : (
          <BellOff className="h-4 w-4 shrink-0 text-ink-500" aria-hidden="true" />
        )}
        <div>
          <div className="text-sm font-medium text-ink-900">
            {status === "on" ? "Reminders are on" : "Reminders are off"}
          </div>
          <div className="text-xs text-ink-500">
            {status === "denied"
              ? "Notifications are blocked. You can allow them in your browser's site settings."
              : "A morning note, plus a heads-up 5 minutes before appointments."}
          </div>
          {error && (
            <div role="alert" className="mt-1 text-xs text-clay-500">
              {error}
            </div>
          )}
        </div>
      </div>
      {status === "denied" ? null : status === "on" ? (
        <button onClick={handleDisable} disabled={busy} className="btn-ghost text-xs">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-label="Working…" /> : "Turn off"}
        </button>
      ) : (
        <button onClick={handleEnable} disabled={busy} className="btn-primary text-xs">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-label="Working…" /> : "Turn on reminders"}
        </button>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  sublabel,
  Icon,
  href,
}: {
  label: string;
  value: number | string;
  sublabel: string;
  Icon: React.ComponentType<{ className?: string }>;
  href: string;
}) {
  return (
    <Link
      to={href}
      // A compact row on phones, a tall card from `sm` up.
      className="card group flex items-center gap-4 p-4 transition-all duration-300 hover:-translate-y-1 hover:border-sage-300 hover:shadow-lift sm:block sm:p-6"
    >
      <div className="flex shrink-0 items-start justify-between">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sage-50 text-sage-600 transition-all duration-300 group-hover:scale-110 group-hover:bg-sage-100">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </div>
        <ArrowRight className="hidden h-4 w-4 -translate-x-1 text-ink-500 opacity-0 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100 sm:block" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1 sm:mt-3">
        <div className="font-serif text-2xl font-semibold tabular-nums text-ink-900 sm:text-3xl">
          {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
        </div>
        <div className="mt-0.5 text-sm text-ink-700">{label}</div>
        <div className="mt-1 text-xs text-ink-500">{sublabel}</div>
      </div>
      <ArrowRight className="h-4 w-4 shrink-0 text-ink-500 sm:hidden" aria-hidden="true" />
    </Link>
  );
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Late night";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  if (h < 21) return "Good evening";
  return "Good night";
}
