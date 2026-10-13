import type { Metadata, Viewport } from "next";
import { BRAND } from "@devgrill/config/brand";
import { themeColors } from "@devgrill/tokens";
import { ThemeProvider, themeInitScript } from "@devgrill/ui/theme";
import { fontVariables } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  // Absolute base for Open Graph / Twitter image URLs.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: `${BRAND.name}: ${BRAND.tagline}`, template: `%s · ${BRAND.name}` },
  description: BRAND.description,
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: themeColors.light.canvas },
    { media: "(prefers-color-scheme: dark)", color: themeColors.dark.canvas },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The theme script sets class/data-motion before paint; React must not "fix" them.
    <html lang="en" suppressHydrationWarning className={fontVariables}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-dvh">
        {/* First Tab stop on every page; every template has a <main id="main">. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[var(--z-toast)] focus:rounded-sm focus:bg-surface focus:px-3 focus:py-2 focus:text-body focus:shadow-float"
        >
          Skip to content
        </a>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
