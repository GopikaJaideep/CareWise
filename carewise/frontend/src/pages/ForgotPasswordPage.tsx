import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Heart, ArrowRight, Loader2, MailCheck } from "lucide-react";
import { api } from "../lib/api";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.forgotPassword(email);
    } finally {
      // Always show the same confirmation, whether or not the email exists —
      // this page never reveals which emails are registered.
      setSent(true);
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

        {sent ? (
          <div className="card text-center">
            <MailCheck className="mx-auto h-8 w-8 text-sage-600" />
            <h1 className="mt-3 font-serif text-2xl font-semibold text-ink-900">Check your email</h1>
            <p className="mt-2 text-sm text-ink-600">
              If an account exists for <strong>{email}</strong>, we've sent a link to reset your
              password. It expires in 30 minutes.
            </p>
            <Link to="/login" className="btn-primary mt-6 inline-flex">
              Back to sign in
            </Link>
          </div>
        ) : (
          <>
            <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink-900">
              Forgot your password?
            </h1>
            <p className="mt-2 text-sm text-ink-600">
              Enter your email and we'll send you a link to reset it.
            </p>

            <form onSubmit={handleSubmit} className="mt-8 space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-ink-800">Email</label>
                <input
                  autoFocus
                  required
                  type="email"
                  className="input-field"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </div>

              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    Send reset link
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-ink-600">
              <Link to="/login" className="font-medium text-sage-700 hover:underline">
                Back to sign in
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
