import { Link } from "react-router-dom";
import { Heart, ShieldCheck, Activity, Calendar, BookOpen, Battery, ArrowRight } from "lucide-react";

const FEATURES = [
  {
    Icon: Heart,
    title: "Emotional companion",
    body: "A calm, non-judgmental presence that listens — not a therapist, but a friend who's actually awake at 2am.",
  },
  {
    Icon: Activity,
    title: "Symptom tracking",
    body: "Tell it in plain language. \"Mum had nausea this morning, about a 6.\" It captures the structure so the team sees patterns.",
  },
  {
    Icon: Calendar,
    title: "Care coordination",
    body: "Appointments, medications, errands. One place. Nothing falling through the cracks at the worst possible moment.",
  },
  {
    Icon: BookOpen,
    title: "Information you can trust",
    body: "Plain-language answers grounded in vetted sources — Cancer Council, NCCN, ACS. Always cited, never prescriptive.",
  },
  {
    Icon: Battery,
    title: "Burnout monitoring",
    body: "A 30-second check-in tracks your own wellbeing over time. Because you can't pour from an empty cup.",
  },
  {
    Icon: ShieldCheck,
    title: "Safety-first AI",
    body: "Crisis content gets a deterministic, audited response with verified resources. No LLM creativity in the safety path.",
  },
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-sand-50">
      {/* Background texture */}
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_-10%,rgba(186,207,182,0.35),transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_90%_30%,rgba(244,226,216,0.5),transparent_55%)]" />
      </div>

      {/* Nav */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-600 text-white shadow-soft">
            <Heart className="h-4 w-4" fill="currentColor" />
          </div>
          <span className="font-serif text-lg font-semibold tracking-tight text-ink-900">CareWise</span>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/login" className="btn-ghost">Sign in</Link>
          <Link to="/register" className="btn-primary">Get started</Link>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-4xl px-6 pt-10 pb-20 text-center md:pt-20">
        <div className="inline-flex items-center gap-2 rounded-full border border-sand-200 bg-white/80 px-3 py-1 text-xs font-medium text-ink-700 shadow-soft animate-fade-in">
          <span className="h-1.5 w-1.5 rounded-full bg-sage-500 animate-pulse-soft" />
          An AI companion for cancer caregivers
        </div>

        <h1 className="mt-6 font-serif text-5xl font-semibold leading-[1.05] tracking-tight text-ink-900 md:text-6xl animate-slide-up">
          For those who hold<br />
          <span className="italic text-sage-700">someone else up</span>.
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-ink-700 animate-slide-up" style={{ animationDelay: "100ms" }}>
          Caring for someone with cancer is full of invisible labour — appointments, side effects,
          medications, fear, exhaustion. CareWise is the steady, attentive companion sitting
          alongside it all.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3 animate-slide-up" style={{ animationDelay: "200ms" }}>
          <Link to="/register" className="btn-primary">
            Start using CareWise
            <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href="#how-it-works"
            className="btn-ghost"
          >
            How it works
          </a>
        </div>

        <p className="mt-8 text-xs text-ink-500">
          Free during portfolio preview · Built with safety-first AI guardrails
        </p>
      </section>

      {/* Features */}
      <section id="how-it-works" className="mx-auto max-w-6xl px-6 pb-24">
        <div className="mb-12 max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-wider text-sage-700">
            Five specialists, one companion
          </p>
          <h2 className="mt-2 font-serif text-3xl font-semibold tracking-tight text-ink-900 md:text-4xl">
            CareWise routes your message to the right specialist agent — automatically.
          </h2>
        </div>

        <div className="grid gap-px bg-sand-200 rounded-2xl overflow-hidden md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ Icon, title, body }, i) => (
            <div
              key={title}
              className="bg-sand-50 p-7 hover:bg-white transition-colors"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sage-50 text-sage-600">
                <Icon className="h-5 w-5" />
              </div>
              <h3 className="mt-5 font-serif text-xl font-semibold text-ink-900">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-700">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Architecture note */}
      <section className="mx-auto max-w-4xl px-6 pb-24">
        <div className="card bg-gradient-to-br from-white to-sand-100/50">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sage-600 text-white">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-serif text-xl font-semibold text-ink-900">
                Built with responsible AI principles
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-700">
                CareWise follows healthcare-AI design principles: an agentic orchestrator with
                cycle protection, deterministic crisis-response paths (no LLM creativity in safety-critical
                code), explicit medical-boundary enforcement, retrieval-grounded resource answers with
                source citation, and PII redaction in logs. The system never diagnoses, never recommends
                dosages, and always defers to the treatment team.
              </p>
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-sand-200 bg-white/40 px-6 py-8">
        <div className="mx-auto max-w-6xl text-center text-sm text-ink-500">
          CareWise · A portfolio project by Gopika · This is not medical advice. In a crisis, call Lifeline
          on 13 11 14 (AU) or your local emergency number.
        </div>
      </footer>
    </div>
  );
}
