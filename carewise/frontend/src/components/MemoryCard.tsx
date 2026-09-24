import { useEffect, useState } from "react";
import { Brain, Loader2, X } from "lucide-react";
import { api, type MemoryState } from "../lib/api";

/** "What CareWise remembers": opt-in memory between chats, fully visible and deletable. */
export function MemoryCard() {
  const [state, setState] = useState<MemoryState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.memory().then(setState).catch(() => setError("Couldn't load what CareWise remembers."));
  }, []);

  const act = async (action: () => Promise<MemoryState | void>, failure: string) => {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setState(next ?? (await api.memory()));
    } catch {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const turnOff = () => {
    if (!window.confirm("Turn off memory? CareWise will also forget everything it remembers.")) return;
    act(() => api.setMemoryEnabled(false), "Couldn't turn memory off. Please try again.");
  };

  const forgetAll = () => {
    if (!window.confirm("Forget everything CareWise remembers? This can't be undone.")) return;
    act(() => api.forgetAllMemory(), "Couldn't forget everything. Please try again.");
  };

  return (
    <section className="card mt-6" aria-labelledby="memory-heading">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sage-50 text-sage-600">
          <Brain className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h2 id="memory-heading" className="font-serif text-xl font-semibold text-ink-900">
            What CareWise remembers
          </h2>
          <p className="text-sm text-ink-600">
            {state?.enabled ? "Memory is on. You can forget anything here." : "Memory is off."}
          </p>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm text-clay-500">
          {error}
        </p>
      )}

      {!state ? (
        !error && (
          <div role="status" className="mt-4 flex items-center gap-2 text-sm text-ink-600">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Loading…
          </div>
        )
      ) : !state.enabled ? (
        <div className="mt-4">
          <p className="text-sm text-ink-700">
            CareWise can remember key things you tell it, like when treatment is or what helps you
            unwind, so you don't have to repeat yourself in each new chat. Everything it remembers is
            listed here for you to delete. It never keeps contact details, ID numbers, or anything
            about a crisis.
          </p>
          <button
            onClick={() => act(() => api.setMemoryEnabled(true), "Couldn't turn memory on. Please try again.")}
            disabled={busy}
            className="btn-primary mt-4"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Working…" /> : "Turn on memory"}
          </button>
        </div>
      ) : (
        <div className="mt-4">
          {state.items.length === 0 ? (
            <p className="text-sm text-ink-600">
              Nothing yet. After a few messages in chat, key things you mention will appear here.
            </p>
          ) : (
            <ul className="space-y-2">
              {state.items.map((item) => (
                <li
                  key={item.id}
                  className="flex items-start justify-between gap-3 rounded-lg border border-sand-200 bg-sand-50 px-3 py-2 text-sm text-ink-800"
                >
                  <span>{item.text}</span>
                  <button
                    onClick={() => act(() => api.forgetMemory(item.id), "Couldn't forget that. Please try again.")}
                    disabled={busy}
                    aria-label={`Forget: ${item.text}`}
                    title="Forget this"
                    className="-mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-500 hover:bg-sand-100 hover:text-ink-900"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {state.items.length > 0 && (
              <button onClick={forgetAll} disabled={busy} className="btn-ghost">
                Forget everything
              </button>
            )}
            <button onClick={turnOff} disabled={busy} className="btn-ghost">
              Turn off memory
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
