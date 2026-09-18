import { Link } from "react-router-dom";
import { BookOpen, ExternalLink, ArrowRight } from "lucide-react";

const RESOURCES = [
  {
    category: "Symptom management",
    items: [
      {
        title: "Understanding cancer-related fatigue",
        prompt: "What helps with cancer-related fatigue?",
      },
      {
        title: "Managing nausea during treatment",
        prompt: "How can we manage nausea during chemo?",
      },
      {
        title: "When appetite drops",
        prompt: "What can I do when she won't eat?",
      },
    ],
  },
  {
    category: "Caregiver wellbeing",
    items: [
      {
        title: "Caregiver burnout — what it is and what helps",
        prompt: "What is caregiver burnout and what helps?",
      },
      {
        title: "Talking with the medical team productively",
        prompt: "How can I prepare for an oncology appointment?",
      },
    ],
  },
  {
    category: "Practical support (Australia)",
    items: [
      {
        title: "Financial support and carer payments",
        prompt: "What financial support is available for carers in Australia?",
      },
    ],
  },
];

const ORGANISATIONS = [
  {
    name: "Cancer Council Australia",
    description: "13 11 20 — free information, support and counselling for anyone affected by cancer.",
    url: "https://www.cancer.org.au",
  },
  {
    name: "Carer Gateway",
    description: "1800 422 737 — Australian government's free counselling, peer support, and respite for unpaid carers.",
    url: "https://www.carergateway.gov.au",
  },
  {
    name: "Lifeline",
    description: "13 11 14 — 24/7 crisis support and suicide prevention.",
    url: "https://www.lifeline.org.au",
  },
  {
    name: "Beyond Blue",
    description: "1300 22 4636 — support for anxiety, depression, and emotional wellbeing.",
    url: "https://www.beyondblue.org.au",
  },
];

export function ResourcesPage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 md:px-6">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sage-50 text-sage-600">
            <BookOpen className="h-5 w-5" />
          </div>
          <div>
            <h1 className="font-serif text-3xl font-semibold tracking-tight">Resources</h1>
            <p className="mt-1 text-sm text-ink-600">
              Plain-language information from vetted sources. Tap any topic to ask CareWise about it.
            </p>
          </div>
        </div>

        {RESOURCES.map((group) => (
          <section key={group.category} className="mt-8">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-500">
              {group.category}
            </h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {group.items.map((item) => (
                <Link
                  key={item.title}
                  to="/app/chat"
                  state={{ initialPrompt: item.prompt }}
                  className="group rounded-xl border border-sand-200 bg-white p-4 shadow-soft transition-all hover:border-sage-300 hover:shadow-lift"
                >
                  <div className="font-medium text-ink-900">{item.title}</div>
                  <div className="mt-1 flex items-center gap-1 text-xs text-sage-700">
                    Ask CareWise
                    <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                  </div>
                </Link>
              ))}
            </div>
          </section>
        ))}

        <section className="mt-12">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-500">
            Australian support organisations
          </h2>
          <div className="mt-3 space-y-2">
            {ORGANISATIONS.map((org) => (
              <a
                key={org.name}
                href={org.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block rounded-xl border border-sand-200 bg-white p-4 shadow-soft transition-colors hover:border-sage-300"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-ink-900">{org.name}</div>
                    <div className="mt-0.5 text-sm text-ink-700">{org.description}</div>
                  </div>
                  <ExternalLink className="h-4 w-4 shrink-0 text-ink-500" />
                </div>
              </a>
            ))}
          </div>
        </section>

        <div className="mt-12 rounded-xl bg-clay-50 border border-clay-200 p-4 text-sm text-ink-800">
          <strong className="text-clay-500">Important:</strong> CareWise provides general information,
          not medical advice. Your treatment team knows the specific situation best — always check
          significant decisions with them.
        </div>
      </div>
    </div>
  );
}
