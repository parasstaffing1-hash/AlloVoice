import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import ChatWidget from "@/components/chat-widget";
import { CookieBanner } from "@/components/cookie-banner";
import { Toaster } from "sonner";

const inter = Inter({ subsets: ["latin"] });

export const viewport: Viewport = {
  themeColor: "#f97316",
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  title: "AlloVoice - AI Voice Agents That Actually Work",
  description: "Answer calls, qualify leads, book appointments and take action automatically — 24/7 voice AI infrastructure.",
  manifest: "/manifest.json",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" className="dark">
      <head>
        <link rel="apple-touch-icon" href="/icons/icon-192.png" />
      </head>
      <body className={inter.className}>
        <script dangerouslySetInnerHTML={{ __html: `
          if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
              navigator.serviceWorker.register('/sw.js').catch(() => {});
            });
          }
        ` }} />
        {children}
        <ChatWidget />
        <CookieBanner />
        <Toaster position="bottom-right" richColors theme="dark" />
      </body>
    </html>
  );
}
