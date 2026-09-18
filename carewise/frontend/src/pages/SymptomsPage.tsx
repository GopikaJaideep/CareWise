import { useEffect, useState } from "react";
import { Activity, Pill, Loader2, Plus, X } from "lucide-react";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { api, type Medication, type SymptomLog } from "../lib/api";

export function SymptomsPage() {
  const [symptoms, setSymptoms] = useState<SymptomLog[]>([]);
  const [meds, setMeds] = useState<Medication[]>([]);
  const [loading, setLoading] = useState(true);
  const [showSymptomForm, setShowSymptomForm] = useState(false);
  const [showMedForm, setShowMedForm] = useState(false);

  const load = async () => {
    const [s, m] = await Promise.all([api.symptoms(14), api.medications()]);
    setSymptoms(s);
    setMeds(m);
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const handleDeactivateMed = async (id: number) => {
    await api.deactivateMedication(id);
    setMeds((ms) => ms.filter((m) => m.id !== id));
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-ink-500" />
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
          Log directly below, or tell CareWise in chat — either way it shows up here for the care team to see.
        </p>

        {/* Severity chart */}
        {chartData.length > 0 && (
          <div className="card mt-6">
            <h2 className="font-serif text-lg font-semibold text-ink-900">Last 14 days</h2>
            <p className="text-xs text-ink-500">Average daily severity (1–10)</p>
            <div className="mt-4 h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 8, left: -28, bottom: 0 }}>
                  <XAxis dataKey="date" stroke="#928B83" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis domain={[0, 10]} stroke="#928B83" fontSize={11} tickLine={false} axisLine={false} />
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
              <Activity className="h-4 w-4 text-sage-600" />
              <h2 className="font-serif text-xl font-semibold text-ink-900">Recent symptoms</h2>
            </div>
            <button onClick={() => setShowSymptomForm((v) => !v)} className="btn-ghost text-xs">
              {showSymptomForm ? <X className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
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
              Nothing logged yet. Log one above, or tell CareWise in chat — e.g. "Mum had nausea this morning, around a 6."
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
              <Pill className="h-4 w-4 text-sage-600" />
              <h2 className="font-serif text-xl font-semibold text-ink-900">Active medications</h2>
            </div>
            <button onClick={() => setShowMedForm((v) => !v)} className="btn-ghost text-xs">
              {showMedForm ? <X className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
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
              No medications tracked. Add one above, or tell CareWise in chat — e.g., "Add ondansetron 8mg, twice a day."
            </div>
          ) : (
            <div className="space-y-2">
              {meds.map((m) => (
                <div
                  key={m.id}
                  className="group flex animate-pop-in items-center justify-between rounded-xl border border-sand-200 bg-white p-3.5 shadow-soft transition-all duration-300 hover:border-sage-200 hover:shadow-lift"
                >
                  <div>
                    <div className="font-medium text-ink-900 capitalize">{m.name}</div>
                    <div className="text-sm text-ink-700">
                      {m.dosage} · {m.schedule}
                    </div>
                    {m.notes && <div className="mt-1 text-xs text-ink-500">{m.notes}</div>}
                  </div>
                  <button
                    onClick={() => handleDeactivateMed(m.id)}
                    className="rounded-lg px-2 py-1 text-xs text-ink-500 opacity-0 transition-all duration-200 hover:bg-sand-100 hover:scale-105 group-hover:opacity-100"
                  >
                    Stop taking
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symptom.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit({ symptom: symptom.trim(), severity, notes: notes.trim() || undefined });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="card mb-4 animate-slide-up">
      <input
        autoFocus
        type="text"
        required
        className="input-field"
        placeholder="What symptom? (e.g. nausea, fatigue, pain)"
        value={symptom}
        onChange={(e) => setSymptom(e.target.value)}
      />
      <div className="mt-3">
        <label className="text-xs font-medium text-ink-600">Severity: {severity}/10</label>
        <input
          type="range"
          min={1}
          max={10}
          value={severity}
          onChange={(e) => setSeverity(Number(e.target.value))}
          className="mt-1 w-full accent-sage-600"
        />
      </div>
      <input
        type="text"
        className="input-field mt-3"
        placeholder="Notes (optional)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <div className="mt-4 flex justify-end">
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Log symptom"}
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !dosage.trim() || !schedule.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit({
        name: name.trim(),
        dosage: dosage.trim(),
        schedule: schedule.trim(),
        notes: notes.trim() || undefined,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="card mb-4 animate-slide-up">
      <input
        autoFocus
        type="text"
        required
        className="input-field"
        placeholder="Medication name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <div className="mt-3 grid grid-cols-2 gap-3">
        <input
          type="text"
          required
          className="input-field"
          placeholder="Dosage (e.g. 8mg)"
          value={dosage}
          onChange={(e) => setDosage(e.target.value)}
        />
        <input
          type="text"
          required
          className="input-field"
          placeholder="Schedule (e.g. twice a day)"
          value={schedule}
          onChange={(e) => setSchedule(e.target.value)}
        />
      </div>
      <input
        type="text"
        className="input-field mt-3"
        placeholder="Notes (optional)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <div className="mt-4 flex justify-end">
        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add medication"}
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
    <div className={`rounded-full px-3 py-1 text-sm font-semibold ${colorClass}`}>
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
