// API client for CareWise backend
const API_BASE = import.meta.env.VITE_API_BASE || "/api";

/** IANA timezone name (e.g. "Australia/Sydney") so the backend can interpret "Tuesday at 10". */
function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export class APIError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function getToken(): string | null {
  return localStorage.getItem("carewise_token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("carewise_token", token);
  else localStorage.removeItem("carewise_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new APIError(detail, res.status);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// --- Types ---
export interface User {
  id: number;
  email: string;
  display_name: string;
  care_recipient_name: string | null;
  care_recipient_relation: string | null;
  diagnosis_context: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  display_name: string;
}

export interface AgentTrace {
  agent: string;
  metadata: Record<string, unknown>;
}

export interface ChatResponse {
  conversation_id: number;
  message_id: number;
  content: string;
  agent_trace: AgentTrace[];
  risk_level: string | null;
}

export interface MessageOut {
  id: number;
  role: string;
  content: string;
  agent_used: string | null;
  created_at: string;
}

export interface ConversationSummary {
  id: number;
  title: string;
  created_at: string;
}

export interface ConversationOut {
  id: number;
  title: string;
  created_at: string;
  messages?: MessageOut[];
}

export interface SymptomLog {
  id: number;
  symptom: string;
  severity: number;
  notes: string | null;
  logged_at: string;
}

export interface Medication {
  id: number;
  name: string;
  dosage: string;
  schedule: string;
  notes: string | null;
  active: boolean;
}

export interface CareTask {
  id: number;
  title: string;
  description: string | null;
  due_at: string | null;
  completed: boolean;
  category: string;
}

export interface BurnoutCheckin {
  id: number;
  sleep_hours: number;
  stress_level: number;
  energy_level: number;
  self_care_minutes: number;
  notes: string | null;
  burnout_score: number;
  created_at: string;
}

export interface DashboardSummary {
  open_tasks_count: number;
  today_tasks_count: number;
  recent_symptom_count: number;
  latest_burnout_score: number | null;
  burnout_category: string | null;
  burnout_trend: number[];
  active_medications: number;
  quote_of_the_day: string;
}

// --- Endpoints ---
export const api = {
  register: (data: {
    email: string;
    password: string;
    display_name: string;
    care_recipient_name?: string;
    care_recipient_relation?: string;
    diagnosis_context?: string;
  }) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>("/auth/me"),

  forgotPassword: (email: string) =>
    request<void>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, new_password: string) =>
    request<void>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password }),
    }),

  chat: (message: string, conversation_id?: number) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, conversation_id, timezone: browserTimezone() }),
    }),

  conversations: () => request<ConversationSummary[]>("/chat/conversations"),

  conversation: (id: number) =>
    request<ConversationOut>(`/chat/conversations/${id}`),

  symptoms: (days = 14) => request<SymptomLog[]>(`/symptoms?days=${days}`),

  logSymptom: (data: { symptom: string; severity: number; notes?: string }) =>
    request<SymptomLog>("/symptoms", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  medications: () => request<Medication[]>("/medications"),

  addMedication: (data: {
    name: string;
    dosage: string;
    schedule: string;
    notes?: string;
  }) =>
    request<Medication>("/medications", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  deactivateMedication: (id: number) =>
    request<Medication>(`/medications/${id}/deactivate`, { method: "PATCH" }),

  tasks: (includeCompleted = false) =>
    request<CareTask[]>(`/tasks?include_completed=${includeCompleted}`),

  createTask: (data: {
    title: string;
    description?: string;
    due_at?: string;
    category?: string;
  }) =>
    request<CareTask>("/tasks", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  completeTask: (id: number) =>
    request<CareTask>(`/tasks/${id}/complete`, { method: "PATCH" }),

  burnoutCheckins: (limit = 30) =>
    request<BurnoutCheckin[]>(`/burnout/checkins?limit=${limit}`),

  dashboard: () =>
    request<DashboardSummary>(`/dashboard?tz=${encodeURIComponent(browserTimezone())}`),

  vapidPublicKey: () => request<{ public_key: string }>("/push/vapid-public-key"),

  subscribePush: (subscription: PushSubscriptionJSON) =>
    request<void>("/push/subscribe", {
      method: "POST",
      body: JSON.stringify(subscription),
    }),

  unsubscribePush: (endpoint: string) =>
    request<void>(`/push/subscribe?endpoint=${encodeURIComponent(endpoint)}`, {
      method: "DELETE",
    }),
};
