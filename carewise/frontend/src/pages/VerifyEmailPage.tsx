import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Heart, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { usePageTitle } from "../lib/usePageTitle";

/** Opened from the confirmation link emailed at sign-up. */
export function VerifyEmailPage() {
  usePageTitle("Confirm your email");
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { user, refreshUser } = useAuth();
  const [status, setStatus] = useState<"working" | "done" | "failed">(token ? "working" : "failed");
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return; // once, even under React StrictMode
    started.current = true;
    api
      .verifyEmail(token)
      .then(() => {
        setStatus("done");
        refreshUser(); // clears the banner if they're signed in on this device
      })
      .catch(() => setStatus("failed"));
  }, [token, refreshUser]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-sand-50 px-6 py-12">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-sage-600 text-white shadow-soft">
          <Heart className="h-5 w-5" fill="currentColor" aria-hidden="true" />
        </div>
        {status === "working" && (
          <p role="status" className="mt-8 flex items-center justify-center gap-2 text-ink-600">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Confirming your email…
          </p>
        )}
        {status === "done" && (
          <>
            <CheckCircle2 className="mx-auto mt-8 h-8 w-8 text-sage-600" aria-hidden="true" />
            <h1 className="mt-3 font-serif text-3xl font-semibold text-ink-900">Email confirmed</h1>
            <p className="mt-2 text-ink-600">Thank you. That's all we needed.</p>
            <Link to={user ? "/app" : "/login"} className="btn-primary mt-8">
              {user ? "Go to CareWise" : "Sign in"}
            </Link>
          </>
        )}
        {status === "failed" && (
          <>
            <h1 className="mt-8 font-serif text-3xl font-semibold text-ink-900">This link didn't work</h1>
            <p className="mt-2 text-ink-600">
              It may have expired or already been replaced by a newer one. Sign in and use
              "Resend the link" to get a fresh one.
            </p>
            <Link to={user ? "/app" : "/login"} className="btn-primary mt-8">
              {user ? "Go to CareWise" : "Sign in"}
            </Link>
          </>
        )}
      </div>
    </main>
  );
}
