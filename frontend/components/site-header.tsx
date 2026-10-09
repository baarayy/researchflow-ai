"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/documents", label: "Documents" },
];

const linkClass =
  "rounded-md px-2 py-1.5 text-muted-foreground sm:px-3 transition-colors hover:bg-muted hover:text-foreground";

function NavLinks({ pathname }: { pathname?: string }) {
  return NAV.map(({ href, label }) => (
    <Link
      key={href}
      href={href}
      aria-current={pathname === href ? "page" : undefined}
      className={cn(linkClass, pathname === href && "bg-muted text-foreground")}
    >
      {label}
    </Link>
  ));
}

function ActiveNavLinks() {
  return <NavLinks pathname={usePathname()} />;
}

export function SiteHeader() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 60_000 });

  return (
    <header className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:gap-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <FlaskConical aria-hidden className="size-5 text-primary" />
          ResearchFlow <span className="hidden text-muted-foreground sm:inline">AI</span>
        </Link>
        <nav aria-label="Main" className="flex gap-1 text-sm">
          {/* The pathname is request-time data on dynamic routes; render plain links meanwhile. */}
          <Suspense fallback={<NavLinks />}>
            <ActiveNavLinks />
          </Suspense>
        </nav>
        <div className="ml-auto flex items-center gap-2 text-xs">
          {health.data?.demo_mode && (
            <Badge variant="outline" className="hidden border-amber-400 text-amber-700 sm:inline-flex dark:text-amber-300">
              Demo mode · mock providers
            </Badge>
          )}
          {health.isError && <Badge variant="destructive">API offline</Badge>}
        </div>
      </div>
    </header>
  );
}
