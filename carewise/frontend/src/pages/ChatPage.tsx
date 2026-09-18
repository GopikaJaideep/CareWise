import { useEffect, useRef, useState } from "react";
import { Send, Loader2, Sparkles, MessageCircle } from "lucide-react";
import { api, type AgentTrace, type MessageOut } from "../lib/api";
import { AgentBadge } from "../components/AgentBadge";
import { useAuth } from "../lib/auth";

interface DisplayMessage {
  id: string | number;
  role: "user" | "assistant";
  content: string;
  agents?: string[];
  trace?: AgentTrace[];
  riskLevel?: string | null;
  timestamp: Date;
}

const SUGGESTIONS = [
  "I'm so tired today.",
  "Mum had nausea this morning, around a 6.",
  "Remind me she has chemo on Tuesday at 10.",
  "Run a burnout check-in: 5 hours sleep, stress 8, energy 3, 0 minutes for me.",
  "What helps with cancer-related fatigue?",
];

export function ChatPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load most recent conversation on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const convs = await api.conversations();
        if (cancelled) return;
        if (convs.length > 0) {
          const recent = await api.conversation(convs[0].id);
          if (cancelled) return;
          setConversationId(recent.id);
          setMessages(
            (recent.messages || []).map((m: MessageOut) => ({
              id: m.id,
              role: m.role as "user" | "assistant",
              content: m.content,
              agents: m.agent_used ? [m.agent_used] : undefined,
              timestamp: new Date(m.created_at),
            }))
          );
        }
      } catch {
        /* fresh start */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

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
      setConversationId(res.conversation_id);
      const assistantMsg: DisplayMessage = {
        id: res.message_id,
        role: "assistant",
        content: res.content,
        agents: res.agent_trace.map((a) => a.agent),
        trace: res.agent_trace,
        riskLevel: res.risk_level,
        timestamp: new Date(),
      };
      setMessages((m) => [...m, assistantMsg]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reach CareWise. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col bg-sand-50">
      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-fade">
        <div className="mx-auto max-w-3xl px-4 py-8 md:px-6">
          {isEmpty && (
            <div className="flex flex-col items-center justify-center py-16 text-center animate-fade-in">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sage-50 text-sage-600">
                <MessageCircle className="h-6 w-6" />
              </div>
              <h2 className="mt-6 font-serif text-3xl font-semibold tracking-tight text-ink-900">
                Hello{user?.display_name ? `, ${user.display_name}` : ""}.
              </h2>
              <p className="mt-3 max-w-md text-ink-600">
                I'm here to listen, help you keep track of things, or pull up information. Whatever
                you need right now.
              </p>

              <div className="mt-10 grid w-full max-w-xl gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="group rounded-xl border border-sand-200 bg-white p-3.5 text-left text-sm text-ink-800 shadow-soft transition-all hover:border-sage-300 hover:bg-sage-50/40 hover:shadow-lift"
                  >
                    <Sparkles className="mb-1.5 h-3.5 w-3.5 text-sage-600 group-hover:text-sage-700" />
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
            <div className="mt-6 flex items-start gap-3 animate-fade-in">
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

          {error && (
            <div className="mt-4 rounded-lg border border-clay-200 bg-clay-50 p-3 text-sm text-clay-500">
              {error}
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="border-t border-sand-200 bg-white/70 backdrop-blur-sm">
        <div className="mx-auto max-w-3xl px-4 py-4 md:px-6">
          <div className="flex items-end gap-3 rounded-2xl border border-sand-200 bg-white p-2 shadow-soft focus-within:border-sage-300 focus-within:ring-2 focus-within:ring-sage-100">
            <textarea
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
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sage-600 text-white shadow-soft transition-all hover:bg-sage-700 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </button>
          </div>
          <p className="mt-2 text-center text-xs text-ink-500">
            CareWise is a companion, not a clinician. In a crisis, call Lifeline on 13 11 14.
          </p>
        </div>
      </div>
    </div>
  );
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
          <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</p>
        </div>
      </div>
    </div>
  );
}
