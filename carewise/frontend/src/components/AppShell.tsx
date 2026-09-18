import { type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Heart, MessageCircle, LayoutDashboard, Calendar, Activity, LogOut, BookOpen } from "lucide-react";
import { useAuth } from "../lib/auth";

const NAV = [
  { to: "/app", label: "Dashboard", Icon: LayoutDashboard, end: true },
  { to: "/app/chat", label: "Companion", Icon: MessageCircle },
  { to: "/app/tasks", label: "Care plan", Icon: Calendar },
  { to: "/app/symptoms", label: "Symptoms", Icon: Activity },
  { to: "/app/resources", label: "Resources", Icon: BookOpen },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex min-h-screen bg-sand-50">
      <aside className="hidden md:flex w-64 flex-col border-r border-sand-200 bg-white/60 backdrop-blur-sm">
        <Link to="/app" className="flex items-center gap-2 px-6 py-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-600 text-white shadow-soft">
            <Heart className="h-4 w-4" fill="currentColor" />
          </div>
          <div>
            <div className="font-serif text-lg font-semibold text-ink-900">CareWise</div>
            <div className="text-xs text-ink-500">for those who care</div>
          </div>
        </Link>

        <nav className="flex-1 px-3 pt-2">
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
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

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
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="flex flex-1 flex-col">
        <header className="md:hidden flex items-center justify-between border-b border-sand-200 bg-white px-4 py-3">
          <Link to="/app" className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sage-600 text-white">
              <Heart className="h-3.5 w-3.5" fill="currentColor" />
            </div>
            <span className="font-serif text-base font-semibold">CareWise</span>
          </Link>
          <button onClick={handleLogout} className="text-ink-600">
            <LogOut className="h-5 w-5" />
          </button>
        </header>

        <main className="flex-1 overflow-hidden">{children}</main>

        {/* Mobile bottom nav */}
        <nav className="md:hidden grid grid-cols-5 border-t border-sand-200 bg-white">
          {NAV.map(({ to, label, Icon, end }) => {
            const isActive = end
              ? location.pathname === to
              : location.pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                className={`flex flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium ${
                  isActive ? "text-sage-700" : "text-ink-500"
                }`}
              >
                <Icon className="h-5 w-5" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
