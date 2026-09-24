import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Send, Loader2, Sparkles, MessageCircle, History, Plus } from "lucide-react";
import { api, APIError, type AgentTrace, type ConversationSummary, type MessageOut, type TurnTrace } from "../lib/api";
import { AgentBadge } from "../components/AgentBadge";
import { useAuth } from "../lib/auth";
import { usePageTitle } from "../lib/usePageTitle";

interface DisplayMessage {
  id: string | number;
  role: "user" | "assistant";
  content: string;
  agents?: string[];
  trace?: AgentTrace[];
  riskLevel?: string | null;
  turn?: TurnTrace | null;
  timestamp: Date;
}

const SUGGESTIONS = [
  "I'm so tired today.",
  "Mum had nausea this morning, around a 6.",
  "Remind me she has chemo on Tuesday at 10.",
  "What helps with cancer-related fatigue?",
];

/** Turn a failed request into something a stressed person can act on, without technical detail. */
function friendlyError(err: unknown): string {
  if (err instanceof APIError) {
    if (err.status === 401) return "Your session has ended. Please sign in again.";
    if (err.status === 429) return "CareWise is getting a lot of messages right now. Please wait a moment and try again.";
    if (err.status < 500 && err.message) return err.message;
    return "CareWise had trouble replying. Your message is back in the box below, so you can try again.";
  }
  return "We couldn't reach CareWise. Check your connection, then try again. Your message is back in the box below.";
}

function toDisplayMessage(m: MessageOut): DisplayMessage {
  return {
    id: m.id,
    role: m.role as "user" | "assistant",
    content: m.content,
    agents: m.agent_used ? [m.agent_used] : undefined,
    turn: m.turn,
    timestamp: new Date(m.created_at),
  };
}

export function ChatPage() {
  usePageTitle("Chat");
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  // A prompt handed over from another page (e.g. "Ask CareWise" on Resources). Read once on mount.
  const initialPromptRef = useRef<string | null>(
    (location.state as { initialPrompt?: string } | null)?.initialPrompt ?? null
  );
  // Stays true after the prompt is consumed, so a StrictMode re-run doesn't reopen an old chat over the new one.
  const arrivedWithPromptRef = useRef(initialPromptRef.current !== null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const refocusComposerRef = useRef(false);

  const openConversation = async (id: number) => {
    setError(null);
    try {
      const conv = await api.conversation(id);
      setConversationId(conv.id);
      setMessages((conv.messages || []).map(toDisplayMessage));
      setHistoryOpen(false);
    } catch {
      setError("Couldn't open that conversation. Please try again.");
    }
  };

  const startNewChat = () => {
    setConversationId(null);
    setMessages([]);
    setError(null);
    setHistoryOpen(false);
  };

  // On mount: load the chat list and reopen the most recent conversation, or, if we were
  // sent here with a prompt, start a fresh chat with it.
  useEffect(() => {
    let cancelled = false;
    const prompt = initialPromptRef.current;
    if (prompt) {
      initialPromptRef.current = null;
      // Drop the prompt from history state so a refresh doesn't send it again.
      navigate(location.pathname, { replace: true, state: null });
      setHistoryLoading(false);
      send(prompt);
    }
    (async () => {
      try {
        const convs = await api.conversations();
        if (cancelled) return;
        setConversations(convs);
        if (convs.length > 0 && !arrivedWithPromptRef.current) {
          const recent = await api.conversation(convs[0].id);
          if (cancelled) return;
          setConversationId(recent.id);
          setMessages((recent.messages || []).map(toDisplayMessage));
        }
      } catch {
        // Don't hide this: an empty chat that looks like lost history is worse than an error.
        if (!cancelled) setError("Couldn't load your previous chats. They're still saved, so try refreshing the page.");
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // After a send finishes, put the cursor back in the composer. This can't happen inside send()
  // itself because the textarea is still disabled until the re-render.
  useEffect(() => {
    if (!loading && refocusComposerRef.current) {
      refocusComposerRef.current = false;
      textareaRef.current?.focus();
    }
  }, [loading]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    setError(null);

    const userMsg: DisplayMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.chat(text, conversationId ?? undefined);
      if (conversationId === null) {
        // A new conversation was just created; show it in the history list.
        api.conversations().then(setConversations).catch(() => undefined);
      }
      setConversationId(res.conversation_id);
      const assistantMsg: DisplayMessage = {
        id: res.message_id,
        role: "assistant",
        content: res.content,
        agents: res.agent_trace.map((a) => a.agent),
        trace: res.agent_trace,
        riskLevel: res.risk_level,
        turn: res.turn,
        timestamp: new Date(),
      };
      setMessages((m) => [...m, assistantMsg]);
    } catch (err) {
      // Take the unsent message back out of the thread and return it to the composer, so nothing
      // the person typed is lost and it's clear it wasn't delivered.
      setMessages((m) => m.filter((msg) => msg.id !== userMsg.id));
      setInput(text);
      setError(friendlyError(err));
    } finally {
      setLoading(false);
      refocusComposerRef.current = true;
    }
  };

  const isEmpty = messages.length === 0 && !historyLoading;

  const errorBanner = error && (
    <div role="alert" className="mt-4 rounded-lg border border-clay-200 bg-clay-50 p-3 text-sm text-clay-500">
      {error}
    </div>
  );

  return (
    <div className="flex h-full flex-col bg-sand-50">
      <div className="border-b border-sand-200 bg-white/70 backdrop-blur-sm">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-2 md:px-6">
          <button
            onClick={() => setHistoryOpen((o) => !o)}
            aria-expanded={historyOpen}
            className="btn-ghost text-xs"
          >
            <History className="h-3.5 w-3.5" aria-hidden="true" />
            Past chats{conversations.length > 0 ? ` (${conversations.length})` : ""}
          </button>
          <button onClick={startNewChat} className="btn-ghost text-xs">
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            New chat
          </button>
        </div>
        {historyOpen && (
          <div className="mx-auto max-w-3xl animate-fade-in px-4 pb-3 md:px-6">
            {conversations.length === 0 ? (
              <p className="py-2 text-sm text-ink-600">No past chats yet.</p>
            ) : (
              <ul className="max-h-64 space-y-1 overflow-y-auto">
                {conversations.map((c) => (
                  <li key={c.id}>
                    <button
                      onClick={() => openConversation(c.id)}
                      className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-sand-100 ${
                        c.id === conversationId ? "bg-sage-50 text-ink-900" : "text-ink-800"
                      }`}
                    >
                      <span className="truncate">{c.title}</span>
                      <span className="shrink-0 text-xs text-ink-500">{formatWhen(c.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-fade">
        <div className="mx-auto max-w-3xl px-4 py-8 md:px-6" role="log" aria-live="polite" aria-label="Conversation">
          {!isEmpty && <h1 className="sr-only">Chat with CareWise</h1>}

          {/* With an empty thread, show errors up top so they aren't hidden below the suggestions. */}
          {messages.length === 0 && errorBanner}

          {historyLoading && messages.length === 0 && (
            <div role="status" className="flex items-center justify-center gap-2 py-16 text-sm text-ink-600">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Loading your chat…
            </div>
          )}

          {isEmpty && (
            <div className="flex flex-col items-center justify-center py-10 text-center animate-fade-in sm:py-16">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sage-50 text-sage-600">
                <MessageCircle className="h-6 w-6" aria-hidden="true" />
              </div>
              <h1 className="mt-6 font-serif text-3xl font-semibold tracking-tight text-ink-900">
                Hello{user?.display_name ? `, ${user.display_name}` : ""}.
              </h1>
              <p className="mt-3 max-w-md text-ink-600">
                What's on your mind? Vent, log a symptom, add an appointment, or ask a question.
              </p>

              <p className="mt-8 text-xs font-medium text-ink-600">Not sure where to start? Try one:</p>
              <div className="mt-3 grid w-full max-w-xl gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="group rounded-xl border border-sand-200 bg-white p-3.5 text-left text-sm text-ink-800 shadow-soft transition-all duration-300 hover:-translate-y-0.5 hover:border-sage-300 hover:bg-sage-50/40 hover:shadow-lift active:translate-y-0 active:scale-[0.98]"
                  >
                    <Sparkles className="mb-1.5 h-3.5 w-3.5 text-sage-600 transition-transform duration-300 group-hover:scale-125 group-hover:text-sage-700" aria-hidden="true" />
                    <div>{s}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <MessageBubble key={m.id} message={m} prevRole={messages[i - 1]?.role} />
          ))}

          {loading && (
            <div role="status" className="mt-6 flex items-start gap-3 animate-fade-in">
              <span className="sr-only">CareWise is replying…</span>
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sage-100 text-sage-700">
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <div className="flex items-center gap-1 pt-2">
                <span className="h-2 w-2 rounded-full bg-ink-500/40 animate-pulse" />
                <span className="h-2 w-2 rounded-full bg-ink-500/40 animate-pulse" style={{ animationDelay: "150ms" }} />
                <span className="h-2 w-2 rounded-full bg-ink-500/40 animate-pulse" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          )}

          {messages.length > 0 && errorBanner}
        </div>
      </div>

      {/* Composer */}
      <div className="border-t border-sand-200 bg-white/70 backdrop-blur-sm">
        <div className="mx-auto max-w-3xl px-4 py-4 md:px-6">
          <div className="flex items-end gap-3 rounded-2xl border border-sand-200 bg-white p-2 shadow-soft focus-within:border-sage-300 focus-within:ring-2 focus-within:ring-sage-100">
            <label htmlFor="chat-input" className="sr-only">
              Message CareWise
            </label>
            <textarea
              id="chat-input"
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Tell me what's going on…"
              disabled={loading}
              className="flex-1 resize-none bg-transparent px-3 py-2 text-ink-900 placeholder-ink-500 focus:outline-none disabled:opacity-50"
            />
            <button
              onClick={() => send(input)}
              disabled={!input.trim() || loading}
              aria-label="Send message"
              className="group flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sage-600 text-white shadow-soft transition-all duration-200 ease-out hover:-translate-y-0.5 hover:bg-sage-700 hover:shadow-lift disabled:pointer-events-none disabled:opacity-40 active:translate-y-0 active:scale-90 active:duration-75"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Send className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
              )}
            </button>
          </div>
          <p className="mt-2 text-center text-xs text-ink-600">
            Not medical advice. In an emergency call{" "}
            <a href="tel:000" className="underline">000</a>, or Lifeline on{" "}
            <a href="tel:131114" className="underline">13 11 14</a>.
          </p>
        </div>
      </div>
    </div>
  );
}

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function MessageBubble({
  message,
  prevRole,
}: {
  message: DisplayMessage;
  prevRole?: string;
}) {
  const isUser = message.role === "user";
  const isCrisis = message.agents?.includes("safety");
  const showSpacing = prevRole && prevRole !== message.role;

  if (isUser) {
    return (
      <div className={`flex justify-end ${showSpacing ? "mt-6" : "mt-3"} animate-slide-up`}>
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-sage-600 px-4 py-2.5 text-white shadow-soft">
          <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex items-start gap-3 ${showSpacing ? "mt-6" : "mt-4"} animate-slide-up`}>
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
        isCrisis ? "bg-red-50 text-red-700" : "bg-sage-100 text-sage-700"
      }`}>
        <Sparkles className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 max-w-[85%]">
        {message.agents && message.agents.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {message.agents.map((a) => (
              <AgentBadge key={a} agent={a} />
            ))}
          </div>
        )}
        <div
          className={`rounded-2xl rounded-tl-sm px-4 py-3 ${
            isCrisis
              ? "bg-red-50 border border-red-200 text-ink-900"
              : "bg-white border border-sand-200 text-ink-900 shadow-soft"
          }`}
        >
          <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{renderInline(message.content)}</p>
        </div>
        {message.turn && <TurnDetails turn={message.turn} />}
      </div>
    </div>
  );
}

const ROUTE_METHOD: Record<string, string> = {
  shortcut: "a keyword shortcut",
  "follow-up": "a follow-up to its previous question",
  model: "the AI router",
  "demo-fallback": "demo mode (no AI key configured)",
  safety: "the safety check (fixed reply, no AI)",
};

const AGENT_NAME: Record<string, string> = {
  emotional_support: "Emotional support",
  symptom_tracker: "Symptom tracker",
  care_coordinator: "Care coordinator",
  resource_guide: "Resource guide",
  burnout_monitor: "Burnout monitor",
  safety: "Safety response",
  router: "Router",
};

function seconds(ms: number | null | undefined) {
  return ms == null ? "?" : `${(ms / 1000).toFixed(ms < 1000 ? 2 : 1)}s`;
}

/** "How this reply was made": the trace the backend records for each turn (no message text). */
function TurnDetails({ turn }: { turn: TurnTrace }) {
  const route = turn.route ? AGENT_NAME[turn.route] ?? turn.route : "an agent";
  return (
    <details className="group mt-1.5 text-xs text-ink-600">
      <summary className="inline-flex cursor-pointer select-none items-center gap-1 rounded px-1 py-0.5 hover:text-ink-900">
        How this reply was made
        <span className="text-ink-500">· {seconds(turn.total_ms)}</span>
      </summary>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-lg border border-sand-200 bg-sand-50 p-3">
        <dt className="text-ink-500">Routed to</dt>
        <dd>
          {route} by {ROUTE_METHOD[turn.route_method ?? ""] ?? "the router"}
        </dd>
        {turn.agents.length > 1 && (
          <>
            <dt className="text-ink-500">Agents</dt>
            <dd>{turn.agents.map((a) => AGENT_NAME[a] ?? a).join(" → ")}</dd>
          </>
        )}
        {turn.retrieval && (
          <>
            <dt className="text-ink-500">Search</dt>
            <dd>
              {turn.retrieval.mode} search, {turn.retrieval.sections.length} article section
              {turn.retrieval.sections.length === 1 ? "" : "s"} used
            </dd>
          </>
        )}
        <dt className="text-ink-500">AI calls</dt>
        <dd>
          {turn.model_calls.length === 0
            ? "none"
            : turn.model_calls
                .map((c) => `${AGENT_NAME[c.step] ?? c.step} ${seconds(c.latency_ms)}${c.ok ? "" : " (failed)"}`)
                .join(", ")}
        </dd>
        {turn.model_calls.length > 0 && (
          <>
            <dt className="text-ink-500">Tokens</dt>
            <dd>
              {turn.tokens.input.toLocaleString()} in, {turn.tokens.output.toLocaleString()} out
              {turn.tokens.thinking ? `, ${turn.tokens.thinking.toLocaleString()} thinking` : ""}
              {turn.cost_usd != null ? ` · about $${turn.cost_usd.toFixed(4)}` : ""}
            </dd>
          </>
        )}
        {turn.output_filter && (
          <>
            <dt className="text-ink-500">Safety filter</dt>
            <dd>replaced a reply that looked like {turn.output_filter}</dd>
          </>
        )}
        <dt className="text-ink-500">Total</dt>
        <dd>
          {seconds(turn.total_ms)} ({seconds(turn.model_ms)} waiting on the AI)
        </dd>
      </dl>
    </details>
  );
}

/** Agents reply with light markdown; render **bold** as <strong> (as React text, never raw HTML). */
function renderInline(text: string) {
  return text.split(/(\*\*[^*\n]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>
    ) : (
      <span key={i}>{linkify(part)}</span>
    )
  );
}

/** Make https:// links clickable (the resource guide cites its sources). Only http(s), never
 * javascript: or other schemes, and always opened in a new tab without access to this page. */
function linkify(text: string) {
  return text.split(/(https?:\/\/[^\s<>"')]+)/g).map((part, i) => {
    if (!/^https?:\/\//.test(part)) return part;
    const trailing = part.match(/[.,;:!?]+$/)?.[0] ?? "";
    const url = trailing ? part.slice(0, -trailing.length) : part;
    return (
      <span key={i}>
        <a href={url} target="_blank" rel="noopener noreferrer" className="break-all text-sage-700 underline underline-offset-2">
          {url}
        </a>
        {trailing}
      </span>
    );
  });
}
