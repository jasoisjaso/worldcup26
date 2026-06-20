"use client"

import { useEffect, useState } from "react"
import { ExternalLink, MessageSquare, AlertTriangle, Newspaper } from "lucide-react"

type News = {
  title: string
  url: string
  source: string | null
  date: string | null
  score: number
}

type Thread = {
  title: string
  url: string
  upvotes: number | null
  comments: number | null
  subreddit: string | null
  date: string | null
  score: number
}

type Quote = {
  body: string
  author: string
  upvotes: number
  url: string
}

type Flag = {
  kind: string
  context: string
  source: string
  url: string | null
}

type TeamEntry = {
  news: News | null
  thread: Thread | null
  quote: Quote | null
  flags: Flag[]
}

type Snapshot = {
  updated_at: string
  teams: Record<string, TeamEntry>
}

function relativeDate(iso?: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso + "T00:00:00Z")
  if (Number.isNaN(d.getTime())) return null
  const days = Math.round((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return "today"
  if (days === 1) return "1 day ago"
  if (days < 7) return `${days} days ago`
  if (days < 14) return "last week"
  return `${Math.round(days / 7)} weeks ago`
}

function fmt(n: number | null | undefined): string {
  if (n == null) return ""
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
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

export function TeamNewsCard({ code, teamName }: { code: string; teamName: string }) {
  const [data, setData] = useState<TeamEntry | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch("/data/team-news.json", { cache: "force-cache" })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((snap: Snapshot) => {
        if (cancelled) return
        const entry = snap.teams?.[code] ?? null
        setData(entry)
        setUpdatedAt(snap.updated_at)
        if (!entry || (!entry.news && !entry.thread && !entry.quote && (entry.flags?.length ?? 0) === 0)) {
          setMissing(true)
        }
      })
      .catch(() => {
        if (!cancelled) setMissing(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [code])

  if (loading) {
    return (
      <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-5 mb-5 animate-pulse">
        <div className="h-3 w-24 bg-white/[0.05] rounded mb-3" />
        <div className="h-4 w-3/4 bg-white/[0.05] rounded mb-2" />
        <div className="h-3 w-1/2 bg-white/[0.05] rounded" />
      </div>
    )
  }

  if (missing || !data) return null

  const hasAnything = !!(data.news || data.thread || data.quote || data.flags?.length)
  if (!hasAnything) return null

  return (
    <section className="rounded-2xl border border-edge bg-surface-2 shadow-e1 mb-5 overflow-hidden">
      <header className="flex items-center justify-between px-5 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <Newspaper size={14} className="text-emerald-400" />
          <h2 className="text-[12px] font-bold uppercase tracking-widest text-slate-300">
            What people are saying
          </h2>
        </div>
        {updatedAt && (
          <span className="text-[10px] text-slate-600">
            Updated {relativeDate(updatedAt.slice(0, 10))}
          </span>
        )}
      </header>

      <div className="px-5 pb-4 space-y-3">
        {/* Injury / availability flags */}
        {data.flags && data.flags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {data.flags.map((f, i) => (
              <a
                key={i}
                href={f.url ?? "#"}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/10 border border-amber-500/30 text-[10.5px] font-semibold text-amber-200 hover:bg-amber-500/15 transition-colors"
                title={f.context}
              >
                <AlertTriangle size={11} />
                {FLAG_LABEL[f.kind] ?? f.kind}
              </a>
            ))}
          </div>
        )}

        {/* Top news article */}
        {data.news && (
          <a
            href={data.news.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block group"
          >
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-1">
              {data.news.source ?? "News"}
              {data.news.date && (
                <span className="ml-2 normal-case tracking-normal font-normal text-slate-600">
                  · {relativeDate(data.news.date)}
                </span>
              )}
            </p>
            <p className="text-[13.5px] font-semibold leading-snug text-slate-100 group-hover:text-emerald-300 transition-colors">
              {data.news.title}
              <ExternalLink size={11} className="inline ml-1 -mt-0.5 text-slate-500" />
            </p>
          </a>
        )}

        {/* Top community thread + quote */}
        {(data.thread || data.quote) && (
          <div className="pt-3 mt-3 border-t border-edge/60">
            {data.quote ? (
              <a
                href={data.quote.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block group"
              >
                <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-1.5 flex items-center gap-1.5">
                  <MessageSquare size={10} />
                  Community
                </p>
                <blockquote className="text-[13px] italic leading-snug text-slate-200 group-hover:text-slate-100 transition-colors">
                  &ldquo;{data.quote.body}&rdquo;
                </blockquote>
                <p className="text-[10.5px] text-slate-500 mt-1.5">
                  {data.quote.author} · {fmt(data.quote.upvotes)} upvotes
                </p>
              </a>
            ) : data.thread ? (
              <a
                href={data.thread.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block group"
              >
                <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-1.5 flex items-center gap-1.5">
                  <MessageSquare size={10} />
                  Community
                </p>
                <p className="text-[13px] font-semibold leading-snug text-slate-200 group-hover:text-emerald-300 transition-colors">
                  {data.thread.title}
                </p>
                <p className="text-[10.5px] text-slate-500 mt-1">
                  {data.thread.subreddit}
                  {data.thread.upvotes != null && ` · ${fmt(data.thread.upvotes)} upvotes`}
                  {data.thread.comments != null && ` · ${fmt(data.thread.comments)} comments`}
                </p>
              </a>
            ) : null}
          </div>
        )}
      </div>

      {/* If the quote led the section, surface the parent thread as a small link */}
      {data.quote && data.thread && (
        <a
          href={data.thread.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block px-5 py-2 border-t border-edge/60 text-[10.5px] text-slate-500 hover:text-slate-300 hover:bg-white/[0.02] transition-colors"
        >
          Read the full thread on {data.thread.subreddit ?? "Reddit"}
          <ExternalLink size={10} className="inline ml-1 -mt-0.5" />
        </a>
      )}
    </section>
  )
}
