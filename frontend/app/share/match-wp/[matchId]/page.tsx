import { TopBar } from "@/components/layout/TopBar"
import Link from "next/link"
import type { Metadata } from "next"

interface PageProps {
  params: { matchId: string }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const url = `https://wc26.tinjak.com/share/match-wp/${params.matchId}`
  return {
    title: "Save this moment: WC2026 win probability",
    description: "Live win probability shifts captured by the WC26 Predictor model.",
    openGraph: {
      title: "Save this moment: WC2026 win probability",
      description: "A shareable snapshot of the live model probabilities.",
      url,
    },
    twitter: { card: "summary_large_image" },
  }
}

export default function ShareMatchWpPage({ params }: PageProps) {
  return (
    <>
      <TopBar title="Save this moment" subtitle="Share the swing chart at this minute" />
      <div className="max-w-3xl mx-auto px-3 sm:px-5 py-6 space-y-4">
        <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4">
          <p className="text-[12px] text-slate-400 leading-relaxed">
            This URL renders a 1200×630 social-share image of the model&apos;s
            win-probability chart for the match. Drop the link into Twitter, WhatsApp,
            or any chat app. The preview auto-generates.
          </p>
          <div className="rounded-lg border border-edge bg-surface-1 mt-3 p-3 font-mono text-[11.5px] text-slate-300 break-all">
            https://wc26.tinjak.com/share/match-wp/{params.matchId}
          </div>
        </div>

        <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
          <img
            src={`/share/match-wp/${params.matchId}/opengraph-image`}
            alt="Live win-probability chart"
            className="w-full"
          />
        </div>

        <Link
          href={`/match/${params.matchId}`}
          className="block text-center text-[12px] text-emerald-400 hover:text-emerald-300"
        >
          ← Back to the match page
        </Link>
      </div>
    </>
  )
}
