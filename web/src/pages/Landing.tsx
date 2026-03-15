import { Link } from "react-router";
import {
  Check,
  ArrowRight,
  Zap,
  Shield,
  Code2,
  Users,
  Layout,
  Globe,
} from "lucide-react";
import { useAuth } from "../auth";
import { Button } from "../components/Button";
import { Badge } from "../components/Badge";
import { ManifoldIcon } from "../components/ManifoldIcon";

export function Landing() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="flex flex-col min-h-screen">
      {/* Hero Section */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-4 py-24 md:py-32 bg-surface">
        <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-700 slide-in-from-bottom-4">
          <Badge
            variant="secondary"
            className="px-4 py-1.5 text-sm rounded-full"
          >
            <span className="mr-2 text-primary">●</span>
            Continuous Security Monitoring
          </Badge>

          <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-text leading-tight">
            Secure your systems
            <span className="text-primary block mt-2">with confidence.</span>
          </h1>

          <p className="text-xl md:text-2xl text-text-muted max-w-2xl mx-auto leading-relaxed">
            Manifold provides continuous cybersecurity monitoring with
            topology visualization, LLM-powered analysis, and role-based
            access control. Focus on shipping, not firefighting.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
            {isAuthenticated ? (
              <Link to="/dashboard">
                <Button size="lg" className="h-14 px-8 text-lg rounded-2xl">
                  Go to Dashboard <ArrowRight className="ml-2 w-5 h-5" />
                </Button>
              </Link>
            ) : (
              <>
                <Link to="/register">
                  <Button
                    size="lg"
                    className="h-14 px-8 text-lg rounded-2xl"
                    data-testid="landing-register"
                  >
                    Get Started
                  </Button>
                </Link>
                <Link to="/login">
                  <Button
                    variant="outline"
                    size="lg"
                    className="h-14 px-8 text-lg rounded-2xl"
                  >
                    View Demo
                  </Button>
                </Link>
              </>
            )}
          </div>

          <div className="pt-8 text-sm text-text-muted">
            Powered by <span className="font-semibold text-text">FastAPI</span>{" "}
            and <span className="font-semibold text-text">React</span> ·{" "}
            <span className="font-semibold text-text">Manifold</span>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="py-24 bg-surface-alt/50 border-y border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold tracking-tight mb-4">
              Everything you need to ship
            </h2>
            <p className="text-text-muted text-lg max-w-2xl mx-auto">
              Focus on your product logic, not the infrastructure. We handle the
              boring stuff.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: Shield,
                title: "Secure by Default",
                desc: "Passkey authentication, RBAC, and secure headers out of the box.",
              },
              {
                icon: Zap,
                title: "Lightning Fast",
                desc: "Optimized Vite build, React 19, and efficient API routes.",
              },
              {
                icon: Layout,
                title: "Modern UI",
                desc: "Beautiful, accessible components built with Tailwind CSS.",
              },
              {
                icon: Code2,
                title: "Developer Experience",
                desc: "TypeScript, hot reloading, and fully typed API client.",
              },
              {
                icon: Users,
                title: "User Management",
                desc: "Complete flow for registration, login, and profile settings.",
              },
              {
                icon: Globe,
                title: "Edge Ready",
                desc: "Deploy anywhere. Docker-ready and scalable architecture.",
              },
            ].map((feature, i) => (
              <div
                key={i}
                className="bg-surface p-8 rounded-3xl border border-border hover:border-primary/50 transition-colors shadow-sm"
              >
                <div className="w-12 h-12 bg-primary/10 rounded-2xl flex items-center justify-center mb-6 text-primary">
                  <feature.icon className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold mb-3">{feature.title}</h3>
                <p className="text-text-muted leading-relaxed">
                  {feature.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section (Demo) */}
      <section className="py-24 bg-surface px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <Badge variant="outline" className="mb-4">
              Example Component
            </Badge>
            <h2 className="text-3xl font-bold tracking-tight mb-4">
              Simple, transparent pricing
            </h2>
            <p className="text-text-muted text-lg">
              Use this section to showcase your product's value.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 items-center">
            {/* Starter Plan */}
            <div className="p-8 rounded-3xl border border-border bg-surface-alt/30">
              <h3 className="font-semibold text-lg mb-2">Starter</h3>
              <div className="text-4xl font-bold mb-6">Free</div>
              <ul className="space-y-4 mb-8 text-text-muted">
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> 1 User
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> 5 Projects
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> Community Support
                </li>
              </ul>
              <Button variant="outline" className="w-full rounded-xl">
                Get Started
              </Button>
            </div>

            {/* Pro Plan */}
            <div className="p-8 rounded-3xl border-2 border-primary bg-surface relative shadow-xl transform md:-translate-y-4">
              <div className="absolute top-0 right-0 bg-primary text-white text-xs font-bold px-3 py-1 rounded-bl-xl rounded-tr-lg">
                POPULAR
              </div>
              <h3 className="font-semibold text-lg mb-2">Pro</h3>
              <div className="text-4xl font-bold mb-6">
                $29
                <span className="text-lg text-text-muted font-normal">/mo</span>
              </div>
              <ul className="space-y-4 mb-8 text-text-muted">
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> Unlimited Users
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> Unlimited Projects
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> Priority Support
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> Advanced Analytics
                </li>
              </ul>
              <Button size="lg" className="w-full rounded-xl">
                Get Started
              </Button>
            </div>

            {/* Enterprise Plan */}
            <div className="p-8 rounded-3xl border border-border bg-surface-alt/30">
              <h3 className="font-semibold text-lg mb-2">Enterprise</h3>
              <div className="text-4xl font-bold mb-6">Custom</div>
              <ul className="space-y-4 mb-8 text-text-muted">
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> Dedicated Support
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> SLA
                </li>
                <li className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-primary" /> Custom Integrations
                </li>
              </ul>
              <Button variant="outline" className="w-full rounded-xl">
                Contact Sales
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-surface border-t border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-2 font-bold text-lg">
            <div className="p-1.5 bg-primary/10 rounded-lg">
              <ManifoldIcon className="w-5 h-5 text-primary" />
            </div>
            <span>Manifold</span>
          </div>
          <div className="flex gap-8 text-sm text-text-muted">
            <a href="#" className="hover:text-text transition-colors">
              Product
            </a>
            <a href="#" className="hover:text-text transition-colors">
              Features
            </a>
            <a href="#" className="hover:text-text transition-colors">
              Pricing
            </a>
            <a href="#" className="hover:text-text transition-colors">
              About
            </a>
          </div>
          <div className="text-sm text-text-muted">
            &copy; {new Date().getFullYear()} Manifold. All rights
            reserved.
          </div>
        </div>
      </footer>
    </div>
  );
}
