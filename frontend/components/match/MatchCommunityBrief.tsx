"use client"

import { useEffect, useState } from "react"
import { ExternalLink, MessageSquare, AlertTriangle, Newspaper } from "lucide-react"

type Thread = {
  title: string
  url: string
  upvotes: number | null
  comments: number | null
  subreddit: string | null
  date: string | null
  score: number
  first_seen?: string
}

type Quote = {
  body: string
  author: string
  upvotes: number
  url: string
  first_seen?: string
}

type News = {
  title: string
  url: string
  source: string | null
  date: string | null
  score: number
  first_seen?: string
}

type Severity = "long_term" | "muscle" | "knock" | null

type Flag = {
  kind: string
  context: string
  source: string
  url: string | null
  severity?: Severity
}

function isNew(iso?: string | null): boolean {
  if (!iso) return false
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return false
  return Date.now() - d.getTime() < 24 * 3600 * 1000
}

function NewBadge({ iso }: { iso?: string | null }) {
  if (!isNew(iso)) return null
  return (
    <span className="ml-1.5 inline-flex items-center align-middle rounded bg-cyan-500/15 border border-cyan-500/40 px-1.5 py-0.5 text-[10.5px] font-bold uppercase tracking-wider text-cyan-200">
      New
    </span>
  )
}

const FLAG_SEVERITY_CLS: Record<NonNullable<Severity>, string> = {
  long_term: "bg-rose-500/10 border-rose-500/30 text-rose-200 hover:bg-rose-500/15",
  muscle:    "bg-amber-500/10 border-amber-500/30 text-amber-200 hover:bg-amber-500/15",
  knock:     "bg-slate-500/10 border-slate-500/30 text-slate-200 hover:bg-slate-500/15",
}
const FLAG_DEFAULT_CLS =
  "bg-amber-500/10 border-amber-500/30 text-amber-200 hover:bg-amber-500/20"

type Sentiment = "panic" | "praise" | "mixed" | null

type MatchBrief = {
  match_id: string
  home_code: string
  away_code: string
  kickoff: string | null
  harvested_at: string | null
  news: News | null
  thread: Thread | null
  quote: Quote | null
  flags: Flag[]
  sentiment?: Sentiment
}

const SENTIMENT_BADGE: Record<NonNullable<Sentiment>, { dot: string; label: string; cls: string }> = {
  panic:  { dot: "🔴", label: "Panic",  cls: "bg-rose-500/10   border-rose-500/30   text-rose-200" },
  praise: { dot: "🟢", label: "Praise", cls: "bg-emerald-500/10 border-emerald-500/30 text-emerald-200" },
  mixed:  { dot: "🟡", label: "Mixed",  cls: "bg-amber-500/10  border-amber-500/30  text-amber-200" },
}

function SentimentBadge({ sentiment }: { sentiment: Sentiment }) {
  if (!sentiment) return null
  const cfg = SENTIMENT_BADGE[sentiment]
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${cfg.cls}`}
      title={`Community vibe: ${cfg.label.toLowerCase()}`}
    >
      <span aria-hidden>{cfg.dot}</span>
      {cfg.label}
    </span>
  )
}

type Snapshot = {
  updated_at: string
  matches: Record<string, MatchBrief>
}

const FLAG_LABEL: Record<string, string> = {
  injury: "injury chatter",
  doubt: "fitness doubt",
  suspension: "suspension chatter",
  "ruled out": "ruled out reports",
  miss: "expected to miss",
  fitness: "fitness concern",
  "red card": "red card",
}

function fmtCount(n: number | null | undefined): string {
  if (n == null) return ""
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function relativeHours(iso?: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const hrs = Math.round((Date.now() - d.getTime()) / 3600000)
  if (hrs < 1) return "just now"
  if (hrs === 1) return "1h ago"
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  if (days === 1) return "1 day ago"
  return `${days} days ago`
}

export function MatchCommunityBrief({ matchId }: { matchId: string }) {
  const [brief, setBrief] = useState<MatchBrief | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetch("/data/match-briefs.json", { cache: "force-cache" })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((snap: Snapshot) => {
        if (cancelled) return
        const entry = snap.matches?.[matchId] ?? null
        setBrief(entry)
      })
      .catch(() => {
        // Quiet failure — surface nothing rather than a broken card.
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [matchId])

  if (loading) return null
  if (!brief) return null

  const hasAny = brief.thread || brief.quote || brief.news || (brief.flags?.length ?? 0) > 0
  if (!hasAny) return null

  const ago = relativeHours(brief.harvested_at)

  return (
    <section className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">What the crowd is saying</p>
        <div className="flex items-center gap-2">
          <SentimentBadge sentiment={brief.sentiment ?? null} />
          {ago && <p className="text-[10px] font-mono text-slate-600">updated {ago}</p>}
        </div>
      </div>

      {brief.flags && brief.flags.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {brief.flags.slice(0, 4).map((f, i) => (
            <a
              key={`${f.kind}-${i}`}
              href={f.url ?? "#"}
              target="_blank"
              rel="noopener noreferrer"
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
                f.severity ? FLAG_SEVERITY_CLS[f.severity] : FLAG_DEFAULT_CLS
              }`}
              title={f.context}
            >
              <AlertTriangle className="w-3 h-3" />
              {FLAG_LABEL[f.kind] ?? f.kind}
            </a>
          ))}
        </div>
      )}

      {brief.thread && (
        <a
          href={brief.thread.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block mb-3 group"
        >
          <div className="flex items-start gap-2">
            <MessageSquare className="w-4 h-4 mt-0.5 shrink-0 text-orange-400" />
            <div className="min-w-0">
              <p className="text-[13px] text-slate-200 group-hover:text-white leading-snug">
                {brief.thread.title}
                <NewBadge iso={brief.thread.first_seen} />
              </p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {brief.thread.subreddit ?? "reddit"}
                {brief.thread.comments != null && ` · ${fmtCount(brief.thread.comments)} comments`}
                {brief.thread.upvotes != null && ` · ${fmtCount(brief.thread.upvotes)} upvotes`}
                <ExternalLink className="inline-block w-3 h-3 ml-1 opacity-60" />
              </p>
            </div>
          </div>
        </a>
      )}

      {brief.quote && (
        <a
          href={brief.quote.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block mb-3 group"
        >
          <blockquote className="border-l-2 border-slate-700 pl-3 text-[13px] text-slate-300 italic leading-snug group-hover:text-slate-200">
            "{brief.quote.body}"
            <NewBadge iso={brief.quote.first_seen} />
          </blockquote>
          <p className="text-[11px] text-slate-500 mt-1 pl-3">
            {brief.quote.author} · {fmtCount(brief.quote.upvotes)} upvotes
            <ExternalLink className="inline-block w-3 h-3 ml-1 opacity-60" />
          </p>
        </a>
      )}

      {brief.news && (
        <a
          href={brief.news.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block group"
        >
          <div className="flex items-start gap-2">
            <Newspaper className="w-4 h-4 mt-0.5 shrink-0 text-sky-400" />
            <div className="min-w-0">
              <p className="text-[13px] text-slate-200 group-hover:text-white leading-snug">
                {brief.news.title}
                <NewBadge iso={brief.news.first_seen} />
              </p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {brief.news.source ?? "web"}
                {brief.news.date && ` · ${brief.news.date}`}
                <ExternalLink className="inline-block w-3 h-3 ml-1 opacity-60" />
              </p>
            </div>
          </div>
        </a>
      )}
    </section>
  )
}
