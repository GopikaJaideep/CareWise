import { useEffect, useState } from "react";
import { Activity, Pill, Loader2 } from "lucide-react";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { api, type Medication, type SymptomLog } from "../lib/api";

export function SymptomsPage() {
  const [symptoms, setSymptoms] = useState<SymptomLog[]>([]);
  const [meds, setMeds] = useState<Medication[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.symptoms(14), api.medications()])
      .then(([s, m]) => {
        setSymptoms(s);
        setMeds(m);
      })
      .finally(() => setLoading(false));
  }, []);

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
          Tell CareWise about symptoms or meds in chat — they'll appear here for the care team to see.
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
          <div className="mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4 text-sage-600" />
            <h2 className="font-serif text-xl font-semibold text-ink-900">Recent symptoms</h2>
          </div>
          {symptoms.length === 0 ? (
            <div className="card text-sm text-ink-600">
              Nothing logged yet. Try saying something like "Mum had nausea this morning, around a 6" in chat.
            </div>
          ) : (
            <div className="space-y-2">
              {symptoms.slice(0, 20).map((s) => (
                <div
                  key={s.id}
                  className="flex items-center justify-between rounded-xl border border-sand-200 bg-white p-3.5 shadow-soft"
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
          <div className="mb-3 flex items-center gap-2">
            <Pill className="h-4 w-4 text-sage-600" />
            <h2 className="font-serif text-xl font-semibold text-ink-900">Active medications</h2>
          </div>
          {meds.length === 0 ? (
            <div className="card text-sm text-ink-600">
              No medications tracked. Tell CareWise in chat — e.g., "Add ondansetron 8mg, twice a day."
            </div>
          ) : (
            <div className="space-y-2">
              {meds.map((m) => (
                <div
                  key={m.id}
                  className="rounded-xl border border-sand-200 bg-white p-3.5 shadow-soft"
                >
                  <div className="font-medium text-ink-900 capitalize">{m.name}</div>
                  <div className="text-sm text-ink-700">
                    {m.dosage} · {m.schedule}
                  </div>
                  {m.notes && <div className="mt-1 text-xs text-ink-500">{m.notes}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
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
