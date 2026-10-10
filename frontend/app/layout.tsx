import type { Metadata, Viewport } from "next";

import "./globals.css";
import { AccessProvider } from "./components/access-provider";
import { AppShell } from "./components/app-shell";

export const metadata: Metadata = {
  title: "Market AI",
  description: "Veille financière structurée et traçable",
  applicationName: "Market AI",
};

export const viewport: Viewport = {
  themeColor: "#111827",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body><AccessProvider><AppShell>{children}</AppShell></AccessProvider></body>
    </html>
  );
}
