import { Link } from "react-router-dom";
import {
  Heart, ShieldCheck, Activity, Calendar, BookOpen, Battery, ArrowRight, Lock, Stethoscope, Phone,
} from "lucide-react";
import { usePageTitle } from "../lib/usePageTitle";

const STEPS = [
  { title: "Create a free account", body: "Takes about a minute. Just your name, email and a password." },
  { title: "Tell CareWise what's going on", body: "Type like you'd text a friend. No forms, no menus." },
  { title: "It keeps track for you", body: "Symptoms, appointments and meds land in the right place, easy to show the care team." },
];

const FEATURES = [
  {
    Icon: Heart,
    title: "Someone to talk to",
    body: "A calm, non-judgemental listener, even at 2am. Not a therapist, and it never pretends to be.",
  },
  {
    Icon: Activity,
    title: "Symptom tracking",
    body: "\"Mum felt sick this morning, about a 6.\" CareWise logs it and charts it over time.",
  },
  {
    Icon: Calendar,
    title: "Care plan",
    body: "Appointments, medications and errands in one list, with optional reminders before each one.",
  },
  {
    Icon: BookOpen,
    title: "Trusted information",
    body: "Plain-language answers drawn from Cancer Council, NCCN and ACS, with the source named.",
  },
  {
    Icon: Battery,
    title: "Check in on yourself",
    body: "A 30-second check-in tracks your own stress and sleep, and points you to support if you're running low.",
  },
  {
    Icon: ShieldCheck,
    title: "Safe in a crisis",
    body: "If you mention being in danger, CareWise gives a fixed, reviewed reply with crisis numbers. No AI improvising.",
  },
];

export function LandingPage() {
  usePageTitle("");

  return (
    <div className="min-h-screen bg-sand-50">
      {/* Background texture */}
      <div className="pointer-events-none fixed inset-0 -z-10" aria-hidden="true">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_-10%,rgba(186,207,182,0.35),transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_90%_30%,rgba(244,226,216,0.5),transparent_55%)]" />
      </div>

      {/* Nav */}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6 sm:py-6">
        <Link to="/" className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-600 text-white shadow-soft">
            <Heart className="h-4 w-4" fill="currentColor" aria-hidden="true" />
          </div>
          <span className="font-serif text-lg font-semibold tracking-tight text-ink-900">CareWise</span>
        </Link>
        <nav aria-label="Account" className="flex items-center gap-1 sm:gap-3">
          <Link to="/login" className="btn-ghost">Sign in</Link>
          <Link to="/register" className="btn-primary">Get started</Link>
        </nav>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 pt-6 pb-16 sm:px-6 md:pt-14 lg:grid-cols-[1.1fr_1fr] lg:gap-14">
          <div className="text-center lg:text-left">
            <h1 className="font-serif text-4xl font-semibold leading-[1.1] tracking-tight text-ink-900 sm:text-5xl md:text-6xl animate-slide-up">
              A calm companion for{" "}
              <span className="italic text-sage-700">cancer caregivers</span>.
            </h1>

            <p
              className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-ink-700 lg:mx-0 animate-slide-up"
              style={{ animationDelay: "100ms" }}
            >
              Talk things through, log symptoms, and keep appointments and medications in one place,
              just by typing like you'd text a friend.
            </p>

            <div
              className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center lg:justify-start animate-slide-up"
              style={{ animationDelay: "200ms" }}
            >
              <Link to="/register" className="btn-primary group w-full px-6 py-3 text-base sm:w-auto">
                Create a free account
                <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1" aria-hidden="true" />
              </Link>
              <a href="#how-it-works" className="btn-ghost">
                See how it works
              </a>
            </div>

            <p className="mt-5 text-sm text-ink-600">
              Free · About a minute to set up · Not a substitute for medical care
            </p>
          </div>

          <ExampleChat />
        </section>

        {/* How it works */}
        <section id="how-it-works" className="scroll-mt-6 border-y border-sand-200 bg-white/50">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <h2 className="font-serif text-3xl font-semibold tracking-tight text-ink-900">How it works</h2>
            <ol className="mt-8 grid gap-6 md:grid-cols-3">
              {STEPS.map((step, i) => (
                <li key={step.title} className="flex gap-4">
                  <span
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sage-600 text-sm font-semibold text-white"
                    aria-hidden="true"
                  >
                    {i + 1}
                  </span>
                  <div>
                    <h3 className="font-sans text-base font-semibold text-ink-900">{step.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-ink-700">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-10">
              <Link to="/register" className="btn-primary group">
                Get started, it's free
                <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-20">
          <h2 className="max-w-2xl font-serif text-3xl font-semibold tracking-tight text-ink-900">
            What CareWise helps with
          </h2>

          <div className="mt-8 grid gap-px overflow-hidden rounded-2xl bg-sand-200 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ Icon, title, body }) => (
              <div key={title} className="bg-sand-50 p-6 sm:p-7">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sage-50 text-sage-600">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </div>
                <h3 className="mt-4 font-serif text-xl font-semibold text-ink-900">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-700">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Safety & privacy */}
        <section id="safety" className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
          <div className="card bg-gradient-to-br from-white to-sand-100/50 sm:p-8">
            <h2 className="font-serif text-2xl font-semibold tracking-tight text-ink-900">
              Safety and privacy, in plain words
            </h2>
            <ul className="mt-6 grid gap-6 md:grid-cols-3">
              <li className="flex gap-3">
                <Stethoscope className="mt-0.5 h-5 w-5 shrink-0 text-sage-600" aria-hidden="true" />
                <div>
                  <h3 className="font-sans text-sm font-semibold text-ink-900">Not a doctor</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-700">
                    CareWise never diagnoses or suggests doses. For anything medical, it points you back
                    to the treatment team.
                  </p>
                </div>
              </li>
              <li className="flex gap-3">
                <Lock className="mt-0.5 h-5 w-5 shrink-0 text-sage-600" aria-hidden="true" />
                <div>
                  <h3 className="font-sans text-sm font-semibold text-ink-900">Your data</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-700">
                    Only you can see your records in the app. Messages are sent to an AI provider
                    (Google Gemini or Anthropic) to write replies, so leave out details like addresses
                    or Medicare numbers.
                  </p>
                </div>
              </li>
              <li className="flex gap-3">
                <Phone className="mt-0.5 h-5 w-5 shrink-0 text-sage-600" aria-hidden="true" />
                <div>
                  <h3 className="font-sans text-sm font-semibold text-ink-900">In a crisis</h3>
                  <p className="mt-1 text-sm leading-relaxed text-ink-700">
                    CareWise isn't an emergency service. Call{" "}
                    <a href="tel:000" className="font-medium text-sage-700 underline">000</a> or Lifeline on{" "}
                    <a href="tel:131114" className="font-medium text-sage-700 underline">13 11 14</a> (24/7).
                  </p>
                </div>
              </li>
            </ul>
          </div>
        </section>
      </main>

      <footer className="border-t border-sand-200 bg-white/40 px-4 py-8 sm:px-6">
        <div className="mx-auto max-w-6xl text-center text-sm text-ink-600">
          <p>
            CareWise is a portfolio project by Gopika. It offers general information, not medical advice.
          </p>
          <p className="mt-1">
            In an emergency call 000. For crisis support call Lifeline on 13 11 14 (Australia), or your
            local emergency number.
          </p>
        </div>
      </footer>
    </div>
  );
}

/** A static, illustrative exchange, so visitors see what using CareWise is actually like. */
function ExampleChat() {
  return (
    <figure
      className="mx-auto w-full max-w-md animate-slide-up rounded-2xl border border-sand-200 bg-white p-4 shadow-lift sm:p-5"
      style={{ animationDelay: "250ms" }}
    >
      <figcaption className="mb-4 flex items-center gap-2 text-xs font-medium text-ink-600">
        <span className="h-1.5 w-1.5 rounded-full bg-sage-500" aria-hidden="true" />
        Example conversation
      </figcaption>
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-sage-600 px-4 py-2.5 text-[15px] leading-relaxed text-white">
          Mum was nauseous after breakfast, about a 6.
        </p>
      </div>
      <div className="mt-3 flex gap-2.5">
        <div
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sage-100 text-sage-700"
          aria-hidden="true"
        >
          <Heart className="h-3.5 w-3.5" fill="currentColor" />
        </div>
        <div className="min-w-0">
          <p className="rounded-2xl rounded-tl-sm border border-sand-200 bg-sand-50 px-4 py-2.5 text-[15px] leading-relaxed text-ink-900">
            I've logged nausea at 6/10 for this morning. If it keeps up, her treatment team can suggest
            anti-nausea options. And how are <em>you</em> holding up?
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-full bg-sage-50 px-2.5 py-0.5 text-xs font-medium text-sage-700 ring-1 ring-inset ring-sage-200">
              <Activity className="h-3 w-3" aria-hidden="true" /> Symptom logged
            </span>
          </div>
        </div>
      </div>
    </figure>
  );
}
