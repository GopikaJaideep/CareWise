import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { AuthProvider, useAuth } from "./lib/auth";
import { LandingPage } from "./pages/LandingPage";
import { AuthPage } from "./pages/AuthPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
// Signed-in pages (and the charting library they use) load on demand, so the landing page stays light.
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const ChatPage = lazy(() => import("./pages/ChatPage").then((m) => ({ default: m.ChatPage })));
const TasksPage = lazy(() => import("./pages/TasksPage").then((m) => ({ default: m.TasksPage })));
const SymptomsPage = lazy(() => import("./pages/SymptomsPage").then((m) => ({ default: m.SymptomsPage })));
const ResourcesPage = lazy(() => import("./pages/ResourcesPage").then((m) => ({ default: m.ResourcesPage })));
const BreathePage = lazy(() => import("./pages/BreathePage").then((m) => ({ default: m.BreathePage })));
import { NotFoundPage } from "./pages/NotFoundPage";
import { AppShell } from "./components/AppShell";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, unreachable } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div role="status" className="flex min-h-screen items-center justify-center bg-sand-50">
        <Loader2 className="h-6 w-6 animate-spin text-ink-500" aria-hidden="true" />
        <span className="sr-only">Loading…</span>
      </div>
    );
  }
  if (!user && unreachable) {
    return <WakingUpScreen />;
  }
  if (!user) {
    return (
      <Navigate
        to="/login"
        state={{ from: location.pathname + location.search + location.hash }}
        replace
      />
    );
  }
  return (
    <AppShell>
      <Suspense
        fallback={
          <div role="status" className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-ink-500" aria-hidden="true" />
            <span className="sr-only">Loading…</span>
          </div>
        }
      >
        {children}
      </Suspense>
    </AppShell>
  );
}

/** Shown when the person is signed in but the server can't be reached yet. Keeps retrying. */
function WakingUpScreen() {
  const { retry, logout } = useAuth();
  return (
    <main className="flex min-h-screen items-center justify-center bg-sand-50 px-6">
      <div className="max-w-sm text-center">
        <Loader2 className="mx-auto h-6 w-6 animate-spin text-sage-600" aria-hidden="true" />
        <h1 className="mt-5 font-serif text-2xl font-semibold text-ink-900">Waking up CareWise…</h1>
        <p role="status" className="mt-2 text-sm text-ink-600">
          The server rests when it's quiet and can take up to a minute to start. You're still signed
          in, and we'll keep trying.
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <button onClick={retry} className="btn-primary">Try now</button>
          <button onClick={logout} className="btn-ghost">Sign out</button>
        </div>
      </div>
    </main>
  );
}

function PublicOnlyRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div role="status" className="flex min-h-screen items-center justify-center bg-sand-50">
        <Loader2 className="h-6 w-6 animate-spin text-ink-500" aria-hidden="true" />
        <span className="sr-only">Loading…</span>
      </div>
    );
  }
  if (user) return <Navigate to="/app" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              <AuthPage mode="login" />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/register"
          element={
            <PublicOnlyRoute>
              <AuthPage mode="register" />
            </PublicOnlyRoute>
          }
        />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/chat"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/tasks"
          element={
            <ProtectedRoute>
              <TasksPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/symptoms"
          element={
            <ProtectedRoute>
              <SymptomsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/resources"
          element={
            <ProtectedRoute>
              <ResourcesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/breathe"
          element={
            <ProtectedRoute>
              <BreathePage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AuthProvider>
  );
}
