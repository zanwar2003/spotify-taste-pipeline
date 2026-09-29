"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/build", label: "Build" },
  { href: "/library", label: "Library" },
];

export function Nav({ signedIn }: { signedIn: boolean }) {
  const pathname = usePathname();
  return (
    <nav className="nav" aria-label="Main">
      <ul>
        {ITEMS.map((item) => (
          <li key={item.href}>
            <Link href={item.href} aria-current={pathname.startsWith(item.href) ? "page" : undefined}>
              {item.label}
            </Link>
          </li>
        ))}
        <li>
          {signedIn ? (
            <form action="/api/auth/logout" method="post">
              <button type="submit">Sign out</button>
            </form>
          ) : (
            <a href="/api/auth/login">Connect Spotify</a>
          )}
        </li>
      </ul>
    </nav>
  );
}
