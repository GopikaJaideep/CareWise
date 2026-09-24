import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Heart, ArrowRight, Loader2 } from "lucide-react";
import { useAuth } from "../lib/auth";
import { APIError } from "../lib/api";
import { usePageTitle } from "../lib/usePageTitle";

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
  usePageTitle(isRegister ? "Create your account" : "Sign in");

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
      else setError("We couldn't reach CareWise. Check your connection and try again.");
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

          <div className="text-xs text-ink-600">
            CareWise is a companion, not a clinician. In a crisis, call Lifeline on 13 11 14.
          </div>
        </div>
      </div>

      {/* Form side */}
      <div className="flex flex-1 items-center justify-center bg-sand-50 px-6 py-12">
        <div className="w-full max-w-md">
          <Link to="/" className="lg:hidden mb-8 flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-600 text-white shadow-soft">
              <Heart className="h-4 w-4" fill="currentColor" aria-hidden="true" />
            </div>
            <span className="font-serif text-lg font-semibold">CareWise</span>
          </Link>

          <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink-900">
            {isRegister ? "Create your free account" : "Welcome back"}
          </h1>
          <p className="mt-2 text-sm text-ink-600">
            {isRegister
              ? "Takes about a minute. Only your name, email and a password are required."
              : "Sign in to pick up where you left off."}
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            {isRegister && (
              <div>
                <label htmlFor="displayName" className="mb-1 block text-sm font-medium text-ink-800">
                  Your first name
                </label>
                <input
                  id="displayName"
                  required
                  type="text"
                  autoComplete="given-name"
                  className="input-field"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="What should we call you?"
                />
              </div>
            )}

            <div>
              <label htmlFor="email" className="mb-1 block text-sm font-medium text-ink-800">Email</label>
              <input
                id="email"
                required
                type="email"
                autoComplete="email"
                className="input-field"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>

            <div>
              <div className="mb-1 flex items-center justify-between">
                <label htmlFor="password" className="block text-sm font-medium text-ink-800">Password</label>
                {!isRegister && (
                  <Link to="/forgot-password" className="text-xs font-medium text-sage-700 hover:underline">
                    Forgot password?
                  </Link>
                )}
              </div>
              <input
                id="password"
                required
                type="password"
                autoComplete={isRegister ? "new-password" : "current-password"}
                minLength={isRegister ? 8 : undefined}
                className="input-field"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isRegister ? "At least 8 characters" : "••••••••"}
              />
            </div>

            {isRegister && (
              <>
                <fieldset className="border-t border-sand-200 pt-4">
                  <legend className="sr-only">About the person you care for (optional)</legend>
                  <p className="mb-3 text-sm font-medium text-ink-800" aria-hidden="true">
                    Who are you caring for? <span className="font-normal text-ink-600">(optional)</span>
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <label htmlFor="careRecipientName" className="mb-1 block text-xs text-ink-600">
                        Their first name
                      </label>
                      <input
                        id="careRecipientName"
                        type="text"
                        autoComplete="off"
                        className="input-field"
                        value={careRecipientName}
                        onChange={(e) => setCareRecipientName(e.target.value)}
                        placeholder="e.g. Anne"
                      />
                    </div>
                    <div>
                      <label htmlFor="careRecipientRelation" className="mb-1 block text-xs text-ink-600">
                        They are your…
                      </label>
                      <input
                        id="careRecipientRelation"
                        type="text"
                        autoComplete="off"
                        className="input-field"
                        value={careRecipientRelation}
                        onChange={(e) => setCareRecipientRelation(e.target.value)}
                        placeholder="e.g. mum, partner"
                      />
                    </div>
                  </div>
                  <label htmlFor="diagnosisContext" className="mb-1 mt-3 block text-xs text-ink-600">
                    Anything about their treatment that would help
                  </label>
                  <textarea
                    id="diagnosisContext"
                    className="input-field min-h-[72px] resize-none"
                    value={diagnosisContext}
                    onChange={(e) => setDiagnosisContext(e.target.value)}
                    placeholder="e.g. Breast cancer, on chemo every 3 weeks"
                  />
                </fieldset>
              </>
            )}

            {error && (
              <div role="alert" className="rounded-lg bg-clay-50 p-3 text-sm text-clay-500 border border-clay-200">
                {error}
                {isRegister && /already registered/i.test(error) && (
                  <>
                    {" "}
                    <Link to="/login" className="font-medium underline">
                      Sign in instead
                    </Link>
                  </>
                )}
              </div>
            )}

            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  {isRegister ? "Creating your account…" : "Signing in…"}
                </>
              ) : (
                <>
                  {isRegister ? "Create account" : "Sign in"}
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </>
              )}
            </button>
            {isRegister && (
              <p className="text-xs leading-relaxed text-ink-600">
                Only you can see your records. Messages are sent to an AI provider to write replies, so
                leave out details like addresses or Medicare numbers. CareWise gives general
                information, not medical advice.
              </p>
            )}
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
