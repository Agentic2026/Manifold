import { Outlet, Link, useLocation } from "react-router";
import { useAuth } from "../auth";
import {
  Sun,
  Moon,
  LogOut,
  LayoutDashboard,
  Settings,
  Radio,
  Menu,
  X,
} from "lucide-react";
import { useState, useEffect } from "react";
import {
  applyEffectiveThemeForPreference,
  applyThemePreference,
  getEffectiveTheme,
  readThemePreference,
  subscribeToSystemThemeChanges,
  type ThemePreference,
} from "../theme";
import { Button } from "./Button";
import { ManifoldIcon } from "./ManifoldIcon";
import { cn } from "../lib/utils";

export function Layout() {
  const { isAuthenticated, logout } = useAuth();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const location = useLocation();

  // Theme logic
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    typeof window === "undefined" ? "system" : readThemePreference(),
  );
  const [systemIsDark, setSystemIsDark] = useState(() =>
    typeof window === "undefined"
      ? false
      : getEffectiveTheme("system") === "dark",
  );
  const effectiveTheme: "light" | "dark" =
    themePreference === "system"
      ? systemIsDark
        ? "dark"
        : "light"
      : themePreference;

  useEffect(() => {
    applyThemePreference(themePreference);
    if (themePreference !== "system") return;
    return subscribeToSystemThemeChanges(() => {
      const effective = applyEffectiveThemeForPreference("system");
      setSystemIsDark(effective === "dark");
    });
  }, [themePreference]);

  useEffect(() => {
    const onPreferenceChange = () => {
      const pref = readThemePreference();
      setThemePreference(pref);
      if (pref === "system") {
        setSystemIsDark(getEffectiveTheme("system") === "dark");
      }
    };
    window.addEventListener("theme-preference-change", onPreferenceChange);
    return () =>
      window.removeEventListener("theme-preference-change", onPreferenceChange);
  }, []);

  // Close mobile menu on route change
  useEffect(() => {
    if (isMobileMenuOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsMobileMenuOpen(false);
    }
  }, [location.pathname, isMobileMenuOpen]);

  const toggleTheme = () => {
    if (themePreference === "system") {
      setThemePreference(effectiveTheme === "dark" ? "light" : "dark");
    } else {
      setThemePreference(themePreference === "light" ? "dark" : "light");
    }
  };

  const navLinks = [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/demo/realtime", label: "Realtime", icon: Radio },
    {
      href: "/settings",
      label: "Settings",
      icon: Settings,
      testId: "nav-settings",
    },
  ];

  return (
    <div className="min-h-screen bg-surface flex flex-col">
      <nav className="border-b border-border bg-surface/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link
              to="/"
              className="flex items-center gap-2 font-bold text-lg text-text hover:text-primary transition-colors"
            >
              <div className="p-1.5 bg-primary/10 rounded-lg">
                <ManifoldIcon className="w-5 h-5 text-primary" />
              </div>
              <span>Manifold</span>
            </Link>

            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center gap-6">
              {isAuthenticated && (
                <div className="flex items-center gap-1">
                  {navLinks.map((link) => {
                    const Icon = link.icon;
                    const isActive = location.pathname === link.href;
                    return (
                      <Link
                        key={link.href}
                        to={link.href}
                        data-testid={link.testId}
                      >
                        <Button
                          variant={isActive ? "secondary" : "ghost"}
                          size="sm"
                          className={cn(
                            "gap-2",
                            isActive ? "text-primary" : "text-text-muted",
                          )}
                        >
                          <Icon className="w-4 h-4" />
                          {link.label}
                        </Button>
                      </Link>
                    );
                  })}
                </div>
              )}

              <div className="h-6 w-px bg-border mx-2" />

              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={toggleTheme}
                  aria-label={
                    themePreference === "system"
                      ? `Theme: system (${effectiveTheme})`
                      : `Theme: ${themePreference}`
                  }
                >
                  {effectiveTheme === "dark" ? (
                    <Sun className="w-4 h-4" />
                  ) : (
                    <Moon className="w-4 h-4" />
                  )}
                </Button>

                {isAuthenticated ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void logout()}
                    className="text-danger hover:text-danger hover:bg-danger/10"
                    data-testid="nav-logout"
                  >
                    <LogOut className="w-4 h-4 mr-2" />
                    Logout
                  </Button>
                ) : (
                  <>
                    <Link to="/login">
                      <Button variant="ghost" size="sm">
                        Login
                      </Button>
                    </Link>
                    <Link to="/register">
                      <Button size="sm">Register</Button>
                    </Link>
                  </>
                )}
              </div>
            </div>

            {/* Mobile Menu Button */}
            <div className="md:hidden flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleTheme}
                className="mr-2"
              >
                {effectiveTheme === "dark" ? (
                  <Sun className="w-4 h-4" />
                ) : (
                  <Moon className="w-4 h-4" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              >
                {isMobileMenuOpen ? (
                  <X className="w-5 h-5" />
                ) : (
                  <Menu className="w-5 h-5" />
                )}
              </Button>
            </div>
          </div>
        </div>

        {/* Mobile Navigation */}
        {isMobileMenuOpen && (
          <div className="md:hidden border-t border-border bg-surface">
            <div className="px-4 py-4 space-y-2">
              {isAuthenticated ? (
                <>
                  {navLinks.map((link) => {
                    const Icon = link.icon;
                    const isActive = location.pathname === link.href;
                    return (
                      <Link
                        key={link.href}
                        to={link.href}
                        className={cn(
                          "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                          isActive
                            ? "bg-primary/10 text-primary"
                            : "text-text-muted hover:bg-surface-alt hover:text-text",
                        )}
                      >
                        <Icon className="w-4 h-4" />
                        {link.label}
                      </Link>
                    );
                  })}
                  <div className="border-t border-border my-2" />
                  <button
                    onClick={() => void logout()}
                    className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-danger hover:bg-danger/10 transition-colors"
                    data-testid="nav-logout-mobile"
                  >
                    <LogOut className="w-4 h-4" />
                    Logout
                  </button>
                </>
              ) : (
                <div className="flex flex-col gap-2">
                  <Link to="/login">
                    <Button variant="secondary" className="w-full justify-start">
                      Login
                    </Button>
                  </Link>
                  <Link to="/register">
                    <Button className="w-full justify-start">Register</Button>
                  </Link>
                </div>
              )}
            </div>
          </div>
        )}
      </nav>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-border py-8 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-text-muted">
          <p>
            &copy; {new Date().getFullYear()} Manifold
          </p>
          <div className="flex gap-6">
            <a href="#" className="hover:text-text transition-colors">
              Terms
            </a>
            <a href="#" className="hover:text-text transition-colors">
              Privacy
            </a>
            <a href="#" className="hover:text-text transition-colors">
              Support
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
