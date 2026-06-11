import type { Metadata, Viewport } from "next"
import { Outfit } from "next/font/google"
import "./globals.css"
import { Sidebar } from "@/components/layout/Sidebar"
import { BottomNav } from "@/components/layout/BottomNav"

const outfit = Outfit({ subsets: ["latin"], weight: ["400", "600", "700", "800"] })

export const metadata: Metadata = {
  metadataBase: new URL("https://wc26.tinjak.com"),
  title: {
    template: "%s | WC2026 Predictor",
    default: "WC2026 Predictor — 2026 FIFA World Cup Match Predictions",
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
    <html lang="en" className="dark">
      <body className={`${outfit.className} bg-[#060a0f] text-slate-200 min-h-screen`}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 min-w-0 overflow-y-auto pb-16 lg:pb-0">{children}</main>
        </div>
        <BottomNav />
      </body>
    </html>
  )
}
