import { type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Heart, MessageCircle, LayoutDashboard, Calendar, Activity, LogOut, BookOpen, Phone } from "lucide-react";
import { useAuth } from "../lib/auth";

const NAV = [
  { to: "/app", label: "Home", Icon: LayoutDashboard, end: true },
  { to: "/app/chat", label: "Chat", Icon: MessageCircle },
  { to: "/app/tasks", label: "Care plan", Icon: Calendar },
  { to: "/app/symptoms", label: "Symptoms", Icon: Activity },
  { to: "/app/resources", label: "Resources", Icon: BookOpen },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    // Pin the shell to the viewport (dvh accounts for mobile browser bars) so each page
    // scrolls inside <main> and the chat composer and bottom nav stay on screen.
    <div className="flex h-screen h-[100dvh] bg-sand-50">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-lift"
      >
        Skip to content
      </a>

      <aside className="hidden md:flex w-64 flex-col border-r border-sand-200 bg-white/60 backdrop-blur-sm">
        <Link to="/app" className="flex items-center gap-2 px-6 py-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-600 text-white shadow-soft">
            <Heart className="h-4 w-4" fill="currentColor" aria-hidden="true" />
          </div>
          <div>
            <div className="font-serif text-lg font-semibold text-ink-900">CareWise</div>
            <div className="text-xs text-ink-500">for those who care</div>
          </div>
        </Link>

        <nav aria-label="Main" className="flex-1 px-3 pt-2">
          {NAV.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-sage-50 text-sage-700"
                    : "text-ink-700 hover:bg-sand-100"
                }`
              }
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mx-3 mb-3 rounded-lg border border-clay-200 bg-clay-50 p-3 text-xs text-ink-700">
          <div className="font-medium text-ink-900">Need to talk to someone now?</div>
          <a href="tel:131114" className="mt-1 inline-flex items-center gap-1 font-medium text-clay-500 hover:underline">
            <Phone className="h-3 w-3" aria-hidden="true" />
            Lifeline 13 11 14
          </a>
          <span className="text-ink-600"> · 24/7</span>
        </div>

        <div className="border-t border-sand-200 p-4">
          <div className="mb-3 px-2">
            <div className="text-sm font-medium text-ink-900">{user?.display_name}</div>
            {user?.care_recipient_name && (
              <div className="text-xs text-ink-500">
                Caring for {user.care_recipient_name}
              </div>
            )}
          </div>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-600 hover:bg-sand-100"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="md:hidden flex items-center justify-between border-b border-sand-200 bg-white px-4 py-2">
          <Link to="/app" className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sage-600 text-white">
              <Heart className="h-3.5 w-3.5" fill="currentColor" aria-hidden="true" />
            </div>
            <span className="font-serif text-base font-semibold">CareWise</span>
          </Link>
          <div className="flex items-center gap-1">
            <a
              href="tel:131114"
              className="flex h-10 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-clay-500 hover:bg-clay-50"
            >
              <Phone className="h-3.5 w-3.5" aria-hidden="true" />
              Crisis line
            </a>
            <button
              onClick={handleLogout}
              aria-label="Sign out"
              title="Sign out"
              className="flex h-10 w-10 items-center justify-center rounded-lg text-ink-600 hover:bg-sand-100"
            >
              <LogOut className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        </header>

        <main id="main" tabIndex={-1} className="relative min-h-0 flex-1 overflow-hidden focus:outline-none">
          {children}
        </main>

        {/* Mobile bottom nav */}
        <nav
          aria-label="Main"
          className="md:hidden grid grid-cols-5 border-t border-sand-200 bg-white pb-[env(safe-area-inset-bottom)]"
        >
          {NAV.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[11px] font-medium ${
                  isActive ? "text-sage-700" : "text-ink-600"
                }`
              }
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
