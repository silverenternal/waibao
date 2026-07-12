import type { Metadata, Viewport } from "next";
// Fonts: use system stack + locally installed via CSS @font-face to avoid
// Google Fonts runtime fetch (which fails in offline / sandbox builds).
import { Providers } from "./providers";
import { Toaster } from "@/components/ui/sonner";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import { OfflineBanner } from "@/components/OfflineBanner";
import { InstallPrompt } from "@/components/InstallPrompt";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";
import { SkipToMain } from "@/components/SkipToMain";
import { ThemeProvider } from "@/components/ThemeProvider";
import { GlobalSearchBar } from "@/components/GlobalSearchBar";
import { organizationJsonLd, SITE_NAME, SITE_URL } from "@/lib/metadata";
import { JsonLd } from "@/components/JsonLd";
import "./globals.css";

// Font CSS variables are defined in globals.css via @font-face with locally
// hosted WOFF2 files under /public/fonts. If the local files are missing we
// fall back to system fonts via the --font-sans / --font-mono CSS vars.

export const metadata: Metadata = {
  title: {
    default: `${SITE_NAME} | AI-Powered Talent Platform`,
    template: `%s | ${SITE_NAME}`,
  },
  description:
    "Intelligent candidate matching, copilot dashboards, and multi-persona workflows for modern recruitment",
  keywords: [
    "recruitment",
    "talent platform",
    "candidate matching",
    "AI hiring",
    "ATS",
    "copilot",
  ],
  authors: [{ name: SITE_NAME }],
  creator: SITE_NAME,
  publisher: SITE_NAME,
  // T1205 — PWA manifest + theme.
  manifest: "/manifest.webmanifest",
  metadataBase: new URL(SITE_URL),
  alternates: {
    canonical: SITE_URL,
    languages: {
      en: `${SITE_URL}/en`,
      zh: `${SITE_URL}/zh`,
      ja: `${SITE_URL}/ja`,
    },
  },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: `${SITE_NAME} | AI-Powered Talent Platform`,
    description:
      "Intelligent candidate matching, copilot dashboards, and multi-persona workflows.",
    url: SITE_URL,
    locale: "en",
    alternateLocale: ["zh", "ja"],
    images: [
      { url: `${SITE_URL}/og-default.png`, width: 1200, height: 630, alt: SITE_NAME },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME} | AI-Powered Talent Platform`,
    description:
      "Intelligent candidate matching, copilot dashboards, and multi-persona workflows.",
    images: [`${SITE_URL}/og-default.png`],
    creator: "@recruittech",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  applicationName: "waibao",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "waibao",
  },
  formatDetection: { telephone: false },
  icons: {
    icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#1772F6",
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();
  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={`h-full antialiased`}
    >
      <head>
        <JsonLd data={organizationJsonLd()} id="jsonld-organization" />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <ThemeProvider>
          <SkipToMain />
          <Providers>
            <NextIntlClientProvider locale={locale} messages={messages}>
              <ServiceWorkerRegister />
              <OfflineBanner />
              <GlobalSearchBar />
              <main id="main-content" tabIndex={-1} className="flex-1 outline-none">
                {children}
              </main>
              <InstallPrompt />
              <Toaster />
            </NextIntlClientProvider>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
