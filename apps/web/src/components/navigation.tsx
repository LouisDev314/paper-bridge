"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/documents", label: "Documents" },
  { href: "/ask", label: "Ask" },
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <header className="nav-shell">
      <div className="nav-brand">PaperBridge</div>
      <nav className="nav-links" aria-label="Main navigation">
        {navItems.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link key={item.href} href={item.href} className={active ? "nav-link nav-link-active" : "nav-link"}>
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
