import { useEffect, useState } from "react";
import { Plus, Check, Loader2, Calendar, Pill, ShoppingBag, FileText } from "lucide-react";
import { api, type CareTask } from "../lib/api";

const CATEGORY_META: Record<string, { Icon: React.ComponentType<{ className?: string }>; label: string }> = {
  appointment: { Icon: Calendar, label: "Appointment" },
  medication: { Icon: Pill, label: "Medication" },
  errand: { Icon: ShoppingBag, label: "Errand" },
  general: { Icon: FileText, label: "General" },
};

export function TasksPage() {
  const [tasks, setTasks] = useState<CareTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newCategory, setNewCategory] = useState("general");
  const [submitting, setSubmitting] = useState(false);
  const [completingIds, setCompletingIds] = useState<Set<number>>(new Set());

  const load = async () => {
    const data = await api.tasks();
    setTasks(data);
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const handleComplete = async (id: number) => {
    setCompletingIds((prev) => new Set(prev).add(id));
    await api.completeTask(id);
    // Let the checkmark-and-strikethrough animation play before the row leaves.
    setTimeout(() => {
      setTasks((ts) => ts.filter((t) => t.id !== id));
      setCompletingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, 550);
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setSubmitting(true);
    try {
      await api.createTask({
        title: newTitle,
        due_at: newDate ? new Date(newDate).toISOString() : undefined,
        category: newCategory,
      });
      setNewTitle("");
      setNewDate("");
      setShowAdd(false);
      await load();
    } finally {
      setSubmitting(false);
    }
  };

  const grouped = groupTasks(tasks);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 md:px-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-serif text-3xl font-semibold tracking-tight">Care plan</h1>
            <p className="mt-1 text-sm text-ink-600">
              Appointments, medications, errands. Add by typing here, or tell CareWise in chat.
            </p>
          </div>
          <button onClick={() => setShowAdd(!showAdd)} className="btn-primary">
            <Plus className="h-4 w-4" /> Add task
          </button>
        </div>

        {showAdd && (
          <form onSubmit={handleAdd} className="card mt-6 animate-slide-up">
            <input
              autoFocus
              type="text"
              required
              className="input-field"
              placeholder="What needs to happen?"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
            <div className="mt-3 grid grid-cols-2 gap-3">
              <input
                type="datetime-local"
                className="input-field"
                value={newDate}
                onChange={(e) => setNewDate(e.target.value)}
              />
              <select
                className="input-field"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
              >
                <option value="general">General</option>
                <option value="appointment">Appointment</option>
                <option value="medication">Medication</option>
                <option value="errand">Errand</option>
              </select>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setShowAdd(false)} className="btn-ghost">
                Cancel
              </button>
              <button type="submit" disabled={submitting} className="btn-primary">
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add"}
              </button>
            </div>
          </form>
        )}

        {loading ? (
          <div className="mt-12 flex justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-ink-500" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="mt-12 text-center text-ink-600">
            <p className="font-serif text-lg">Nothing scheduled.</p>
            <p className="mt-1 text-sm">Add something above, or just tell CareWise in chat.</p>
          </div>
        ) : (
          <div className="mt-8 space-y-8">
            {grouped.today.length > 0 && (
              <Section title="Today" tasks={grouped.today} onComplete={handleComplete} completingIds={completingIds} />
            )}
            {grouped.tomorrow.length > 0 && (
              <Section title="Tomorrow" tasks={grouped.tomorrow} onComplete={handleComplete} completingIds={completingIds} />
            )}
            {grouped.upcoming.length > 0 && (
              <Section title="Upcoming" tasks={grouped.upcoming} onComplete={handleComplete} completingIds={completingIds} />
            )}
            {grouped.undated.length > 0 && (
              <Section title="No date set" tasks={grouped.undated} onComplete={handleComplete} completingIds={completingIds} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  tasks,
  onComplete,
  completingIds,
}: {
  title: string;
  tasks: CareTask[];
  onComplete: (id: number) => void;
  completingIds: Set<number>;
}) {
  return (
    <div>
      <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-500">{title}</h2>
      <div className="mt-3 space-y-2">
        {tasks.map((t) => {
          const meta = CATEGORY_META[t.category] ?? CATEGORY_META.general;
          const Icon = meta.Icon;
          const isCompleting = completingIds.has(t.id);
          return (
            <div
              key={t.id}
              className={`group flex items-center gap-3 rounded-xl border border-sand-200 bg-white p-3.5 shadow-soft transition-all duration-500 ease-out hover:border-sage-200 ${
                isCompleting ? "-translate-x-1 opacity-40" : ""
              }`}
            >
              <button
                onClick={() => onComplete(t.id)}
                disabled={isCompleting}
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-200 ${
                  isCompleting
                    ? "border-sage-500 bg-sage-500"
                    : "border-sand-300 hover:border-sage-500 hover:bg-sage-50"
                }`}
                aria-label="Mark complete"
              >
                <Check
                  className={`h-3.5 w-3.5 transition-colors ${
                    isCompleting ? "animate-check-pop text-white" : "text-transparent group-hover:text-sage-600"
                  }`}
                />
              </button>
              <Icon className="h-4 w-4 shrink-0 text-ink-500" />
              <div className="flex-1 min-w-0">
                <div
                  className={`text-[15px] font-medium truncate transition-all duration-300 ${
                    isCompleting ? "text-ink-500 line-through" : "text-ink-900"
                  }`}
                >
                  {t.title}
                </div>
                {t.due_at && (
                  <div className="text-xs text-ink-500">{formatDateTime(t.due_at)}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function groupTasks(tasks: CareTask[]): {
  today: CareTask[];
  tomorrow: CareTask[];
  upcoming: CareTask[];
  undated: CareTask[];
} {
  const today: CareTask[] = [];
  const tomorrow: CareTask[] = [];
  const upcoming: CareTask[] = [];
  const undated: CareTask[] = [];
  const now = new Date();
  const todayStr = now.toDateString();
  const tomorrowDate = new Date(now);
  tomorrowDate.setDate(tomorrowDate.getDate() + 1);
  const tomorrowStr = tomorrowDate.toDateString();

  for (const t of tasks) {
    if (!t.due_at) {
      undated.push(t);
      continue;
    }
    const d = new Date(t.due_at);
    const ds = d.toDateString();
    if (ds === todayStr) today.push(t);
    else if (ds === tomorrowStr) tomorrow.push(t);
    else upcoming.push(t);
  }

  return { today, tomorrow, upcoming, undated };
}
