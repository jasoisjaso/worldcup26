import type { Metadata, Viewport } from "next"
import { Inter, Space_Grotesk, JetBrains_Mono } from "next/font/google"
import "./globals.css"
import { Sidebar } from "@/components/layout/Sidebar"
import { BottomNav } from "@/components/layout/BottomNav"

const sans = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-sans" })
const display = Space_Grotesk({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-display" })
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500", "700"], variable: "--font-mono" })

export const metadata: Metadata = {
  metadataBase: new URL("https://wc26.tinjak.com"),
  title: {
    template: "%s | WC2026 Predictor",
    default: "WC2026 Predictor: 2026 FIFA World Cup Match Predictions",
  },
  description:
    "Data-driven 2026 FIFA World Cup match predictions. ELO ratings, Poisson model, live odds analysis, value bets, and ACCA builder for all 104 group stage matches.",
  keywords: [
    "World Cup 2026",
    "WC2026 predictions",
    "FIFA World Cup odds",
    "football betting tips",
    "value bets World Cup",
    "ACCA builder",
    "match predictions 2026",
    "World Cup group stage",
  ],
  openGraph: {
    title: "WC2026 Predictor",
    description:
      "Data-driven 2026 FIFA World Cup predictions. ELO + Poisson model with live bookmaker odds analysis.",
    url: "https://wc26.tinjak.com",
    siteName: "WC2026 Predictor",
    type: "website",
    locale: "en_AU",
  },
  twitter: {
    card: "summary_large_image",
    title: "WC2026 Predictor",
    description:
      "Data-driven 2026 FIFA World Cup predictions. Live odds, value bets, ACCA builder.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
    },
  },
  alternates: {
    canonical: "https://wc26.tinjak.com",
  },
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${sans.variable} ${display.variable} ${mono.variable}`}>
      <body className="font-sans bg-surface-0 text-slate-200 min-h-screen antialiased">
        {/* Site-wide grain overlay: breaks the flat banded dark and reads premium */}
        <div className="grain" aria-hidden="true" />
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 min-w-0 overflow-y-auto pb-24 lg:pb-0">{children}</main>
        </div>
        <BottomNav />
      </body>
    </html>
  )
}
