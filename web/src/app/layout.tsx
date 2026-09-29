import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { getSessionUserId } from "@/lib/session";

export const metadata: Metadata = {
  title: "Taste Pipeline: playlists from public Spotify profiles",
  description: "Build a playlist from someone's public Spotify profile, then keep it in your library.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const userId = await getSessionUserId();
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">Skip to main content</a>
        <Nav signedIn={userId !== null} />
        <main id="main" className="container">{children}</main>
      </body>
    </html>
  );
}
