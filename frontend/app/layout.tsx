/**
 * Root layout with global styles, providers, header navigation, and toast notifications
 * Wraps app with all context providers and TanStack Query
 * Updated for Story 6.3 with authentication support
 */

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { QueryProvider } from "@/components/providers/query-provider";
import { AuthProvider } from "@/contexts/AuthContext";
import { NotificationProvider } from "@/contexts/NotificationContext";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { Toaster } from "@/components/ui/sonner";
import { AppShell } from "@/components/layout/AppShell";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ArgusAI",
  description: "AI-powered event detection and monitoring for home security",
  keywords: ["security", "AI", "camera", "monitoring", "event detection"],
  authors: [{ name: "ArgusAI Team" }],
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "ArgusAI",
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [
      { url: "/apple-touch-icon.png", sizes: "180x180" },
      { url: "/icons/apple-touch-icon-120.png", sizes: "120x120" },
      { url: "/icons/apple-touch-icon-152.png", sizes: "152x152" },
      { url: "/icons/apple-touch-icon-167.png", sizes: "167x167" },
      { url: "/icons/apple-touch-icon-180.png", sizes: "180x180" },
    ],
  },
  openGraph: {
    title: "ArgusAI",
    description: "AI-powered event detection and monitoring for home security",
    url: "https://project-argusai.github.io/ArgusAI/",
    siteName: "ArgusAI",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "ArgusAI - AI-Powered Home Security",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "ArgusAI",
    description: "AI-powered event detection and monitoring for home security",
    images: ["/og-image.png"],
  },
  other: {
    "mobile-web-app-capable": "yes",
    "msapplication-TileImage": "/mstile-150x150.png",
    "msapplication-TileColor": "#0a0a0a",
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0a0a0a",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <QueryProvider>
          <ThemeProvider
            attribute="class"
            defaultTheme="system"
            enableSystem
            disableTransitionOnChange
          >
            <SettingsProvider>
              <AuthProvider>
                <NotificationProvider>
                  <AppShell>
                    {children}
                  </AppShell>
                  <Toaster />
                </NotificationProvider>
              </AuthProvider>
            </SettingsProvider>
          </ThemeProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
