import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, APIError, setToken, type User } from "./api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  /** Signed in (a token is saved) but the server can't be reached yet, e.g. while it wakes up. */
  unreachable: boolean;
  retry: () => void;
  login: (email: string, password: string) => Promise<void>;
  register: (data: {
    email: string;
    password: string;
    display_name: string;
    care_recipient_name?: string;
    care_recipient_relation?: string;
    diagnosis_context?: string;
  }) => Promise<void>;
  logout: () => void;
  /** Re-read the signed-in user (e.g. after confirming their email). */
  refreshUser: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [unreachable, setUnreachable] = useState(false);
  const retryTimer = useRef<number>();
  const attempt = useRef(0);

  // Check the saved session. Only a 401 (the server rejected the token) signs the person out.
  // Anything else (network error, 502/503 while a sleeping server on Render wakes up, a deploy
  // restarting it) keeps the session and retries: signing someone out because the server was
  // briefly down forced them to log in again after every deploy.
  const checkSession = useCallback(async () => {
    window.clearTimeout(retryTimer.current);
    if (!localStorage.getItem("carewise_token")) {
      setLoading(false);
      return;
    }
    try {
      setUser(await api.me());
      setUnreachable(false);
      attempt.current = 0;
    } catch (err) {
      if (err instanceof APIError && err.status === 401) {
        setToken(null);
        setUser(null);
        setUnreachable(false);
      } else {
        setUnreachable(true);
        attempt.current += 1;
        // 3s, 6s, 9s... capped at 15s; a cold start on Render's free plan takes up to a minute.
        retryTimer.current = window.setTimeout(checkSession, Math.min(3000 * attempt.current, 15000));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkSession();
    return () => window.clearTimeout(retryTimer.current);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    setToken(res.access_token);
    const me = await api.me();
    setUser(me);
  }, []);

  const register = useCallback(
    async (data: Parameters<AuthContextValue["register"]>[0]) => {
      const res = await api.register(data);
      setToken(res.access_token);
      const me = await api.me();
      setUser(me);
    },
    []
  );

  const refreshUser = useCallback(() => {
    if (!localStorage.getItem("carewise_token")) return;
    api.me().then(setUser).catch(() => undefined);
  }, []);

  const logout = useCallback(() => {
    window.clearTimeout(retryTimer.current);
    setToken(null);
    setUser(null);
    setUnreachable(false);
  }, []);

  const retry = useCallback(() => {
    attempt.current = 0;
    checkSession();
  }, [checkSession]);

  return (
    <AuthContext.Provider value={{ user, loading, unreachable, retry, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
