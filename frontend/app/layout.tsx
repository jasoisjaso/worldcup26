import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { Sidebar } from "@/components/layout/Sidebar"
import { BottomNav } from "@/components/layout/BottomNav"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "WC 2026 Predictor",
  description: "2026 FIFA World Cup match predictions and betting analysis",
  viewport: "width=device-width, initial-scale=1",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-[#0a0d14] text-slate-200 min-h-screen`}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 min-w-0 overflow-y-auto pb-16 lg:pb-0">{children}</main>
        </div>
        <BottomNav />
      </body>
    </html>
  )
}
