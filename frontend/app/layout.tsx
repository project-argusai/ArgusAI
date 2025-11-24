/**
 * Root layout with global styles, providers, header navigation, and toast notifications
 * Wraps app with all context providers and TanStack Query
 */

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { QueryProvider } from "@/components/providers/query-provider";
import { AuthProvider } from "@/contexts/AuthContext";
import { NotificationProvider } from "@/contexts/NotificationContext";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { Toaster } from "@/components/ui/sonner";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { MobileNav } from "@/components/layout/MobileNav";
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
                  <Header />
                  <Sidebar />
                  <main className="min-h-screen bg-background pt-16 pb-16 lg:pb-0 lg:pl-60 transition-all duration-300">
                    <div className="container mx-auto">
                      {children}
                    </div>
                  </main>
                  <MobileNav />
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
