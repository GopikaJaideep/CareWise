import { useEffect, useState } from "react";
import { Activity, Pill, Loader2, Plus, X, RefreshCw } from "lucide-react";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { api, type Medication, type SymptomLog } from "../lib/api";
import { usePageTitle } from "../lib/usePageTitle";

export function SymptomsPage() {
  usePageTitle("Symptoms & medications");
  const [symptoms, setSymptoms] = useState<SymptomLog[]>([]);
  const [meds, setMeds] = useState<Medication[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showSymptomForm, setShowSymptomForm] = useState(false);
  const [showMedForm, setShowMedForm] = useState(false);

  const load = async () => {
    const [s, m] = await Promise.all([api.symptoms(14), api.medications()]);
    setSymptoms(s);
    setMeds(m);
  };

  const initialLoad = () => {
    setLoading(true);
    setLoadFailed(false);
    load()
      .catch(() => setLoadFailed(true))
      .finally(() => setLoading(false));
  };

  useEffect(initialLoad, []);

  const handleDeactivateMed = async (med: Medication) => {
    if (!window.confirm(`Stop tracking ${med.name}? It will be removed from this list.`)) return;
    setActionError(null);
    try {
      await api.deactivateMedication(med.id);
      setMeds((ms) => ms.filter((m) => m.id !== med.id));
    } catch {
      setActionError(`Couldn't remove ${med.name}. Please try again.`);
    }
  };

  if (loading) {
    return (
      <div role="status" className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-ink-500" aria-hidden="true" />
        <span className="sr-only">Loading symptoms and medications…</span>
      </div>
    );
  }

  if (loadFailed) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div role="alert" className="max-w-sm text-center">
          <h1 className="font-serif text-2xl font-semibold text-ink-900">We couldn't load this page</h1>
          <p className="mt-2 text-sm text-ink-600">Your records are safe. Check your connection and try again.</p>
          <button onClick={initialLoad} className="btn-primary mt-6">
            <RefreshCw className="h-4 w-4" aria-hidden="true" /> Try again
          </button>
        </div>
      </div>
    );
  }

  // Build chart data: severity by day for top symptoms
  const chartData = buildChartData(symptoms);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 md:px-6">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Symptoms & medications</h1>
        <p className="mt-1 text-sm text-ink-600">
          Log them here or just mention them in chat. Either way they're saved here, handy for appointments.
        </p>

        {actionError && (
          <div role="alert" className="mt-4 rounded-lg border border-clay-200 bg-clay-50 p-3 text-sm text-clay-500">
            {actionError}
          </div>
        )}

        {/* Severity chart */}
        {chartData.length > 0 && (
          <div className="card mt-6">
            <h2 className="font-serif text-lg font-semibold text-ink-900">Last 14 days</h2>
            <p className="text-xs text-ink-500">Average daily severity (1–10)</p>
            <div
              className="mt-4 h-48"
              role="img"
              aria-label={`Average daily symptom severity over ${chartData.length} day${chartData.length === 1 ? "" : "s"}, on a scale of 1 to 10`}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 8, left: -28, bottom: 0 }}>
                  <XAxis dataKey="date" stroke="#716A62" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 10]} ticks={[0, 5, 10]} stroke="#716A62" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 8,
                      border: "1px solid #E8DFCE",
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="severity" fill="#90B28C" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Symptom list */}
        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-sage-600" aria-hidden="true" />
              <h2 className="font-serif text-xl font-semibold text-ink-900">Recent symptoms</h2>
            </div>
            <button onClick={() => setShowSymptomForm((v) => !v)} aria-expanded={showSymptomForm} className="btn-ghost text-xs">
              {showSymptomForm ? <X className="h-3.5 w-3.5" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              {showSymptomForm ? "Cancel" : "Log symptom"}
            </button>
          </div>

          {showSymptomForm && (
            <SymptomForm
              onSubmit={async (data) => {
                await api.logSymptom(data);
                setShowSymptomForm(false);
                await load();
              }}
            />
          )}

          {symptoms.length === 0 ? (
            <div className="card text-sm text-ink-600">
              Nothing logged in the last 14 days. Tap <strong className="font-medium">Log symptom</strong>, or
              tell CareWise in chat, like "Mum had nausea this morning, around a 6."
            </div>
          ) : (
            <div className="space-y-2">
              {symptoms.slice(0, 20).map((s) => (
                <div
                  key={s.id}
                  className="flex animate-pop-in items-center justify-between rounded-xl border border-sand-200 bg-white p-3.5 shadow-soft transition-all duration-300 hover:border-sage-200 hover:shadow-lift"
                >
                  <div>
                    <div className="font-medium text-ink-900 capitalize">{s.symptom}</div>
                    {s.notes && <div className="text-xs text-ink-600">{s.notes}</div>}
                    <div className="mt-0.5 text-xs text-ink-500">{formatDate(s.logged_at)}</div>
                  </div>
                  <SeverityPill severity={s.severity} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Medications */}
        <div className="mt-8">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Pill className="h-4 w-4 text-sage-600" aria-hidden="true" />
              <h2 className="font-serif text-xl font-semibold text-ink-900">Active medications</h2>
            </div>
            <button onClick={() => setShowMedForm((v) => !v)} aria-expanded={showMedForm} className="btn-ghost text-xs">
              {showMedForm ? <X className="h-3.5 w-3.5" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              {showMedForm ? "Cancel" : "Add medication"}
            </button>
          </div>

          {showMedForm && (
            <MedicationForm
              onSubmit={async (data) => {
                await api.addMedication(data);
                setShowMedForm(false);
                await load();
              }}
            />
          )}

          {meds.length === 0 ? (
            <div className="card text-sm text-ink-600">
              No medications yet. Tap <strong className="font-medium">Add medication</strong>, or tell CareWise
              in chat, like "Add ondansetron 8mg, twice a day."
            </div>
          ) : (
            <div className="space-y-2">
              {meds.map((m) => (
                <div
                  key={m.id}
                  className="group flex animate-pop-in items-center justify-between gap-3 rounded-xl border border-sand-200 bg-white p-3.5 shadow-soft transition-all duration-300 hover:border-sage-200 hover:shadow-lift"
                >
                  <div className="min-w-0">
                    <div className="font-medium text-ink-900 capitalize">{m.name}</div>
                    <div className="text-sm text-ink-700">
                      {m.dosage} · {m.schedule}
                    </div>
                    {m.notes && <div className="mt-1 text-xs text-ink-500">{m.notes}</div>}
                  </div>
                  {/* Always visible on touch screens; on desktop it appears on hover or keyboard focus. */}
                  <button
                    onClick={() => handleDeactivateMed(m)}
                    aria-label={`Stop tracking ${m.name}`}
                    className="shrink-0 rounded-lg px-2 py-1.5 text-xs text-ink-600 transition-all duration-200 hover:bg-sand-100 focus-visible:opacity-100 md:opacity-0 md:group-hover:opacity-100"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SymptomForm({
  onSubmit,
}: {
  onSubmit: (data: { symptom: string; severity: number; notes?: string }) => Promise<void>;
}) {
  const [symptom, setSymptom] = useState("");
  const [severity, setSeverity] = useState(5);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symptom.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ symptom: symptom.trim(), severity, notes: notes.trim() || undefined });
    } catch {
      setError("Couldn't save that. Please check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="card mb-4 animate-slide-up" aria-label="Log a symptom">
      <label htmlFor="symptom-name" className="mb-1 block text-xs font-medium text-ink-600">
        Symptom
      </label>
      <input
        id="symptom-name"
        autoFocus
        type="text"
        required
        className="input-field"
        placeholder="e.g. nausea, fatigue, pain"
        value={symptom}
        onChange={(e) => setSymptom(e.target.value)}
      />
      <div className="mt-3">
        <label htmlFor="symptom-severity" className="text-xs font-medium text-ink-600">
          How bad? {severity}/10 <span className="font-normal">(1 = mild, 10 = worst)</span>
        </label>
        <input
          id="symptom-severity"
          type="range"
          min={1}
          max={10}
          value={severity}
          onChange={(e) => setSeverity(Number(e.target.value))}
          className="mt-1 w-full accent-sage-600"
        />
      </div>
      <label htmlFor="symptom-notes" className="mb-1 mt-3 block text-xs font-medium text-ink-600">
        Notes <span className="font-normal">(optional)</span>
      </label>
      <input
        id="symptom-notes"
        type="text"
        className="input-field"
        placeholder="e.g. after breakfast, eased by evening"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      {error && (
        <p role="alert" className="mt-3 text-sm text-clay-500">
          {error}
        </p>
      )}
      <div className="mt-4 flex justify-end">
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Saving…" /> : "Log symptom"}
        </button>
      </div>
    </form>
  );
}

function MedicationForm({
  onSubmit,
}: {
  onSubmit: (data: {
    name: string;
    dosage: string;
    schedule: string;
    notes?: string;
  }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [dosage, setDosage] = useState("");
  const [schedule, setSchedule] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !dosage.trim() || !schedule.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        name: name.trim(),
        dosage: dosage.trim(),
        schedule: schedule.trim(),
        notes: notes.trim() || undefined,
      });
    } catch {
      setError("Couldn't save that. Please check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="card mb-4 animate-slide-up" aria-label="Add a medication">
      <label htmlFor="med-name" className="mb-1 block text-xs font-medium text-ink-600">
        Medication
      </label>
      <input
        id="med-name"
        autoFocus
        type="text"
        required
        className="input-field"
        placeholder="e.g. ondansetron"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="med-dosage" className="mb-1 block text-xs font-medium text-ink-600">
            Dose
          </label>
          <input
            id="med-dosage"
            type="text"
            required
            className="input-field"
            placeholder="e.g. 8mg"
            value={dosage}
            onChange={(e) => setDosage(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="med-schedule" className="mb-1 block text-xs font-medium text-ink-600">
            How often
          </label>
          <input
            id="med-schedule"
            type="text"
            required
            className="input-field"
            placeholder="e.g. twice a day"
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
          />
        </div>
      </div>
      <label htmlFor="med-notes" className="mb-1 mt-3 block text-xs font-medium text-ink-600">
        Notes <span className="font-normal">(optional)</span>
      </label>
      <input
        id="med-notes"
        type="text"
        className="input-field"
        placeholder="e.g. with food"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <p className="mt-3 text-xs text-ink-600">
        This is just a record for you. Always follow the prescriber's instructions.
      </p>
      {error && (
        <p role="alert" className="mt-3 text-sm text-clay-500">
          {error}
        </p>
      )}
      <div className="mt-4 flex justify-end">
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Saving…" /> : "Add medication"}
        </button>
      </div>
    </form>
  );
}

function SeverityPill({ severity }: { severity: number }) {
  const colorClass =
    severity >= 8
      ? "bg-red-100 text-red-700"
      : severity >= 5
      ? "bg-clay-100 text-clay-500"
      : "bg-sage-100 text-sage-700";
  return (
    <div className={`shrink-0 rounded-full px-3 py-1 text-sm font-semibold ${colorClass}`}>
      <span className="sr-only">Severity </span>
      {severity}/10
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function buildChartData(symptoms: SymptomLog[]): Array<{ date: string; severity: number }> {
  if (symptoms.length === 0) return [];
  const byDay = new Map<string, { sum: number; count: number }>();
  for (const s of symptoms) {
    const d = new Date(s.logged_at);
    const key = d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
    const cur = byDay.get(key) ?? { sum: 0, count: 0 };
    byDay.set(key, { sum: cur.sum + s.severity, count: cur.count + 1 });
  }
  return Array.from(byDay.entries())
    .map(([date, { sum, count }]) => ({ date, severity: Math.round((sum / count) * 10) / 10 }))
    .reverse();
}
