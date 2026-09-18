import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Heart, ArrowRight, Loader2 } from "lucide-react";
import { useAuth } from "../lib/auth";
import { APIError } from "../lib/api";

interface AuthPageProps {
  mode: "login" | "register";
}

export function AuthPage({ mode }: AuthPageProps) {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [careRecipientName, setCareRecipientName] = useState("");
  const [careRecipientRelation, setCareRecipientRelation] = useState("");
  const [diagnosisContext, setDiagnosisContext] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isRegister = mode === "register";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isRegister) {
        await register({
          email,
          password,
          display_name: displayName,
          care_recipient_name: careRecipientName || undefined,
          care_recipient_relation: careRecipientRelation || undefined,
          diagnosis_context: diagnosisContext || undefined,
        });
      } else {
        await login(email, password);
      }
      const next = (location.state as { from?: string } | null)?.from || "/app";
      navigate(next, { replace: true });
    } catch (err) {
      if (err instanceof APIError) setError(err.message);
      else setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Visual side */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-sage-50 via-sand-100 to-clay-50 p-12 relative overflow-hidden">
        <div className="absolute inset-0">
          <div className="absolute top-1/4 left-1/4 h-96 w-96 rounded-full bg-sage-200/40 blur-3xl" />
          <div className="absolute bottom-1/4 right-1/4 h-72 w-72 rounded-full bg-clay-200/40 blur-3xl" />
        </div>
        <div className="relative z-10 flex flex-col justify-between w-full">
          <Link to="/" className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-600 text-white shadow-soft">
              <Heart className="h-4 w-4" fill="currentColor" />
            </div>
            <span className="font-serif text-lg font-semibold">CareWise</span>
          </Link>

          <div className="max-w-md">
            <p className="font-serif text-3xl leading-snug text-ink-800 italic">
              "The expectation that we can be immersed in suffering and loss daily and not be touched by it is as unrealistic as expecting to be able to walk through water without getting wet."
            </p>
            <p className="mt-4 text-sm text-ink-600">— Rachel Naomi Remen</p>
          </div>

          <div className="text-xs text-ink-500">
            CareWise is a companion, not a clinician. In a crisis, please call Lifeline on 13 11 14.
          </div>
        </div>
      </div>

      {/* Form side */}
      <div className="flex flex-1 items-center justify-center bg-sand-50 px-6 py-12">
        <div className="w-full max-w-md">
          <div className="lg:hidden mb-8 flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-600 text-white shadow-soft">
              <Heart className="h-4 w-4" fill="currentColor" />
            </div>
            <span className="font-serif text-lg font-semibold">CareWise</span>
          </div>

          <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink-900">
            {isRegister ? "Welcome to CareWise" : "Welcome back"}
          </h1>
          <p className="mt-2 text-sm text-ink-600">
            {isRegister
              ? "A few details so CareWise can show up the way you need."
              : "Sign in to continue."}
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            {isRegister && (
              <div>
                <label className="mb-1 block text-sm font-medium text-ink-800">Your name</label>
                <input
                  required
                  type="text"
                  className="input-field"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="What should CareWise call you?"
                />
              </div>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium text-ink-800">Email</label>
              <input
                required
                type="email"
                className="input-field"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-ink-800">Password</label>
              <input
                required
                type="password"
                minLength={isRegister ? 8 : undefined}
                className="input-field"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isRegister ? "At least 8 characters" : "••••••••"}
              />
            </div>

            {isRegister && (
              <>
                <div className="border-t border-sand-200 pt-4">
                  <p className="text-xs uppercase tracking-wider text-ink-500 font-medium mb-3">
                    About who you're caring for (optional)
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      type="text"
                      className="input-field"
                      value={careRecipientName}
                      onChange={(e) => setCareRecipientName(e.target.value)}
                      placeholder="Their name"
                    />
                    <input
                      type="text"
                      className="input-field"
                      value={careRecipientRelation}
                      onChange={(e) => setCareRecipientRelation(e.target.value)}
                      placeholder="Relation (e.g. mother)"
                    />
                  </div>
                  <textarea
                    className="input-field mt-3 min-h-[72px] resize-none"
                    value={diagnosisContext}
                    onChange={(e) => setDiagnosisContext(e.target.value)}
                    placeholder="Anything relevant about their treatment or stage that helps CareWise know the context"
                  />
                </div>
              </>
            )}

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
                  {isRegister ? "Create account" : "Sign in"}
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-ink-600">
            {isRegister ? (
              <>
                Already have an account?{" "}
                <Link to="/login" className="font-medium text-sage-700 hover:underline">
                  Sign in
                </Link>
              </>
            ) : (
              <>
                Don't have an account?{" "}
                <Link to="/register" className="font-medium text-sage-700 hover:underline">
                  Create one
                </Link>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
