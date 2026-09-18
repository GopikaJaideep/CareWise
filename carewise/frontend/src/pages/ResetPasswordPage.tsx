import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Heart, ArrowRight, Loader2, CheckCircle2 } from "lucide-react";
import { api, APIError } from "../lib/api";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }

    setLoading(true);
    try {
      await api.resetPassword(token, password);
      setDone(true);
      setTimeout(() => navigate("/login"), 2500);
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-sand-50 px-6 py-12">
      <div className="w-full max-w-md">
        <Link to="/" className="mb-8 flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-600 text-white shadow-soft">
            <Heart className="h-4 w-4" fill="currentColor" />
          </div>
          <span className="font-serif text-lg font-semibold">CareWise</span>
        </Link>

        {!token ? (
          <div className="card text-center">
            <h1 className="font-serif text-2xl font-semibold text-ink-900">Invalid link</h1>
            <p className="mt-2 text-sm text-ink-600">
              This reset link is missing its token. Request a new one below.
            </p>
            <Link to="/forgot-password" className="btn-primary mt-6 inline-flex">
              Request new link
            </Link>
          </div>
        ) : done ? (
          <div className="card text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-sage-600" />
            <h1 className="mt-3 font-serif text-2xl font-semibold text-ink-900">Password updated</h1>
            <p className="mt-2 text-sm text-ink-600">Taking you to sign in…</p>
          </div>
        ) : (
          <>
            <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink-900">
              Set a new password
            </h1>
            <p className="mt-2 text-sm text-ink-600">Choose something you haven't used before.</p>

            <form onSubmit={handleSubmit} className="mt-8 space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-ink-800">New password</label>
                <input
                  autoFocus
                  required
                  type="password"
                  minLength={8}
                  className="input-field"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-ink-800">Confirm password</label>
                <input
                  required
                  type="password"
                  minLength={8}
                  className="input-field"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="Type it again"
                />
              </div>

              {error && (
                <div className="rounded-lg bg-clay-50 p-3 text-sm text-clay-500 border border-clay-200">
                  {error}
                </div>
              )}

              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    Reset password
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
