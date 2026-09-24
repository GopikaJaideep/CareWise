import { Link } from "react-router-dom";
import { Heart } from "lucide-react";
import { usePageTitle } from "../lib/usePageTitle";
import { useAuth } from "../lib/auth";

export function NotFoundPage() {
  usePageTitle("Page not found");
  const { user } = useAuth();

  return (
    <main className="flex min-h-screen items-center justify-center bg-sand-50 px-6 py-12">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-sage-600 text-white shadow-soft">
          <Heart className="h-5 w-5" fill="currentColor" aria-hidden="true" />
        </div>
        <h1 className="mt-6 font-serif text-3xl font-semibold tracking-tight text-ink-900">
          We couldn't find that page
        </h1>
        <p className="mt-2 text-ink-600">The link may be old, or there might be a typo in the address.</p>
        <Link to={user ? "/app" : "/"} className="btn-primary mt-8">
          {user ? "Go to your dashboard" : "Go to the home page"}
        </Link>
      </div>
    </main>
  );
}
