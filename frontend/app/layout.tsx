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
  title: "Live Object AI Classifier",
  description: "AI-powered event detection and monitoring for home security",
  keywords: ["security", "AI", "camera", "monitoring", "event detection"],
  authors: [{ name: "Live Object AI Team" }],
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
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
