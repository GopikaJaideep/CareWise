import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine,
} from "recharts";
import {
  Activity, Calendar, Battery, Pill, ArrowRight, Loader2, MessageCircle,
  BellRing, BellOff, Sparkles,
} from "lucide-react";
import { api, type DashboardSummary } from "../lib/api";
import { useAuth } from "../lib/auth";
import { disablePushReminders, enablePushReminders, pushPermission } from "../lib/push";
import { AnimatedNumber } from "../components/AnimatedNumber";

export function DashboardPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.dashboard().then(setSummary).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-ink-500" />
      </div>
    );
  }
  if (!summary) return null;

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
      ? "text-sand-500"
      : "text-sage-600";

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-8 md:px-6">
        <div className="flex items-baseline justify-between">
          <div>
            <p className="text-sm text-ink-600">{greeting}</p>
            <h1 className="mt-1 font-serif text-3xl font-semibold tracking-tight text-ink-900">
              {user?.display_name ? `Hi, ${user.display_name}` : "Hi"}
            </h1>
          </div>
          <Link to="/app/chat" className="btn-primary">
            <MessageCircle className="h-4 w-4" />
            Talk to CareWise
          </Link>
        </div>

        <div className="mt-6 flex items-start gap-3 rounded-xl border border-sage-200 bg-sage-50 p-4">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-sage-600" />
          <p className="text-sm italic text-ink-800">"{summary.quote_of_the_day}"</p>
        </div>

        <ReminderToggle />

        <div className="mt-8 grid gap-4 md:grid-cols-3">
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
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sage-50 text-sage-600">
                <Battery className="h-5 w-5" />
              </div>
              <div>
                <h2 className="font-serif text-xl font-semibold text-ink-900">Your wellbeing</h2>
                <p className="text-sm text-ink-600">Burnout check-in trend</p>
              </div>
            </div>
            {summary.latest_burnout_score !== null ? (
              <div className="animate-count-up text-right">
                <div className={`font-serif text-3xl font-semibold tabular-nums ${burnoutColor}`}>
                  <AnimatedNumber value={Math.round(summary.latest_burnout_score)} />
                </div>
                <div className="text-xs text-ink-600">/ 100 — {summary.burnout_category}</div>
              </div>
            ) : (
              <Link to="/app/chat" className="btn-ghost">
                Run a check-in <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </div>

          {trendData.length > 1 ? (
            <div className="mt-6 h-32">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <XAxis dataKey="name" stroke="#928B83" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 100]} stroke="#928B83" fontSize={11} tickLine={false} axisLine={false} />
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
              No check-ins yet. Tell CareWise about your sleep, stress, energy, and self-care to start tracking.
            </p>
          )}

          {summary.burnout_category &&
            ["high", "very high"].includes(summary.burnout_category) && (
              <div className="mt-5 rounded-lg bg-clay-50 border border-clay-200 p-3 text-sm text-ink-800">
                <strong className="text-clay-500">A note:</strong> Your recent check-ins show you're
                running close to empty. Carer Gateway (1800 422 737) can arrange free respite — even a
                few hours. Cancer Council 13 11 20 also has free counselling for caregivers.
              </div>
            )}
        </div>

        {/* Quick start prompts */}
        {summary.recent_symptom_count === 0 &&
          summary.open_tasks_count === 0 &&
          summary.latest_burnout_score === null && (
            <div className="card mt-6">
              <h3 className="font-serif text-lg font-semibold text-ink-900">Try saying</h3>
              <p className="mt-1 text-sm text-ink-600">
                CareWise understands plain language. Here are a few starters.
              </p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {[
                  "Mum had nausea this morning, around a 6.",
                  "Add: oncology appointment Tuesday at 10am.",
                  "I'm exhausted. Don't know how to keep going.",
                  "Run a burnout check-in.",
                ].map((s) => (
                  <Link
                    key={s}
                    to="/app/chat"
                    className="rounded-lg border border-sand-200 bg-sand-50 p-3 text-sm text-ink-800 hover:bg-white"
                  >
                    "{s}"
                  </Link>
                ))}
              </div>
            </div>
          )}
      </div>
    </div>
  );
}

function ReminderToggle() {
  const [status, setStatus] = useState<"loading" | "unsupported" | "off" | "on" | "denied">(
    "loading"
  );
  const [busy, setBusy] = useState(false);

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
    try {
      const result = await enablePushReminders();
      setStatus(result.ok ? "on" : result.reason === "denied" ? "denied" : "off");
    } finally {
      setBusy(false);
    }
  };

  const handleDisable = async () => {
    setBusy(true);
    try {
      await disablePushReminders();
      setStatus("off");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 flex items-center justify-between rounded-xl border border-sand-200 bg-white p-3.5 shadow-soft">
      <div className="flex items-center gap-3">
        {status === "on" ? (
          <BellRing className="h-4 w-4 text-sage-600" />
        ) : (
          <BellOff className="h-4 w-4 text-ink-500" />
        )}
        <div>
          <div className="text-sm font-medium text-ink-900">
            {status === "on" ? "Reminders are on" : "Reminders are off"}
          </div>
          <div className="text-xs text-ink-500">
            {status === "denied"
              ? "Notifications are blocked in your browser settings."
              : "A gentle morning quote, plus a heads-up 5 minutes before appointments."}
          </div>
        </div>
      </div>
      {status === "denied" ? null : status === "on" ? (
        <button onClick={handleDisable} disabled={busy} className="btn-ghost text-xs">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Turn off"}
        </button>
      ) : (
        <button onClick={handleEnable} disabled={busy} className="btn-primary text-xs">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Enable reminders"}
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
      className="card group transition-all duration-300 hover:-translate-y-1 hover:border-sage-300 hover:shadow-lift"
    >
      <div className="flex items-start justify-between">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sage-50 text-sage-600 transition-all duration-300 group-hover:scale-110 group-hover:bg-sage-100">
          <Icon className="h-4 w-4" />
        </div>
        <ArrowRight className="h-4 w-4 -translate-x-1 text-ink-500 opacity-0 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100" />
      </div>
      <div className="mt-3 font-serif text-3xl font-semibold tabular-nums text-ink-900">
        {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
      </div>
      <div className="mt-0.5 text-sm text-ink-700">{label}</div>
      <div className="mt-1 text-xs text-ink-500">{sublabel}</div>
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
