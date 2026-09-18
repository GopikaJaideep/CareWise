import { Heart, Activity, Calendar, BookOpen, Battery, ShieldAlert } from "lucide-react";
import type { ComponentType } from "react";

interface AgentBadgeProps {
  agent: string;
}

const AGENT_META: Record<
  string,
  { label: string; Icon: ComponentType<{ className?: string }>; classes: string }
> = {
  emotional_support: {
    label: "Emotional support",
    Icon: Heart,
    classes: "bg-clay-50 text-clay-500 ring-clay-200",
  },
  symptom_tracker: {
    label: "Symptom tracker",
    Icon: Activity,
    classes: "bg-sage-50 text-sage-700 ring-sage-200",
  },
  care_coordinator: {
    label: "Care coordinator",
    Icon: Calendar,
    classes: "bg-sand-100 text-ink-800 ring-sand-300",
  },
  resource_guide: {
    label: "Resource guide",
    Icon: BookOpen,
    classes: "bg-sand-100 text-ink-800 ring-sand-300",
  },
  burnout_monitor: {
    label: "Burnout monitor",
    Icon: Battery,
    classes: "bg-sage-50 text-sage-700 ring-sage-200",
  },
  safety: {
    label: "Safety response",
    Icon: ShieldAlert,
    classes: "bg-red-50 text-red-700 ring-red-200",
  },
};

export function AgentBadge({ agent }: AgentBadgeProps) {
  const meta = AGENT_META[agent] ?? {
    label: agent,
    Icon: Activity,
    classes: "bg-sand-100 text-ink-700 ring-sand-200",
  };
  const { label, Icon, classes } = meta;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${classes}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}
