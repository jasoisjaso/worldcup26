"use client"

import { useCallback, useEffect, useState } from "react"
import { Bell, BellRing } from "lucide-react"
import { ensureSubscribed, getCachedEndpoint, iosInstallRequired, isLikelyEUiOS, pushSupported } from "@/lib/push"

interface FollowBellProps {
  matchId: string
}

/** Google-style "follow this match" bell. Renders on every MatchCard.
 *  - First click on an unsubscribed device: prompts for push permission,
 *    then auto-creates the follow row.
 *  - Subsequent click: toggles follow on/off.
 *  - iOS pre-install: shows a small overlay with Add-to-Home-Screen steps
 *    before triggering the permission prompt (otherwise the prompt is a
 *    no-op and the user gets silent failure).
 *  - EU iOS: disabled with a tooltip pointing at the DMA situation.
 */
export function FollowBell({ matchId }: FollowBellProps) {
  const [following, setFollowing] = useState<boolean>(false)
  const [busy, setBusy] = useState(false)
  const [showIosOverlay, setShowIosOverlay] = useState(false)
  const [available, setAvailable] = useState<boolean | "eu-ios">(false)

  useEffect(() => {
    if (!pushSupported()) { setAvailable(false); return }
    if (isLikelyEUiOS()) { setAvailable("eu-ios"); return }
    setAvailable(true)
    // Hydrate "is this match already followed" from server, but only when
    // we already have an endpoint cached (avoids triggering subscribe on
    // page load).
    const ep = getCachedEndpoint()
    if (!ep) return
    fetch(`/api/push/follows?endpoint=${encodeURIComponent(ep)}`, { cache: "no-store" })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return
        const hit = (d.matches as Array<{ match_id: string }>).some(m => m.match_id === matchId)
        if (hit) setFollowing(true)
      })
      .catch(() => { /* ignore — bell defaults to unfollowed */ })
  }, [matchId])

  const toggle = useCallback(async () => {
    if (busy || available !== true) return
    setBusy(true)
    try {
      // iOS install gate runs BEFORE we even try to subscribe — the
      // permission prompt is a no-op on a non-installed iOS browser.
      if (iosInstallRequired()) {
        setShowIosOverlay(true)
        return
      }
      const ep = await ensureSubscribed()
      if (!ep) return  // user denied permission
      if (!following) {
        const r = await fetch("/api/push/follow-match", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: ep, match_id: matchId }),
        })
        if (r.ok) setFollowing(true)
      } else {
        const r = await fetch("/api/push/unfollow-match", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: ep, match_id: matchId }),
        })
        if (r.ok) setFollowing(false)
      }
    } finally {
      setBusy(false)
    }
  }, [busy, available, following, matchId])

  if (available === false) return null
  if (available === "eu-ios") {
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-slate-600 cursor-not-allowed"
        title="Web Push isn't available on iPhone in the EU yet (Apple removed it under DMA)."
      >
        <Bell size={11} />
      </span>
    )
  }

  // Pill style chosen over a bare icon (2026-06-24): the dim icon was too
  // easy to miss next to BroadcastBadge — users reported "I can't see it".
  // A 'Follow' label removes ambiguity.
  return (
    <>
      <button
        onClick={toggle}
        disabled={busy}
        aria-label={following ? "Unfollow match" : "Follow match"}
        aria-pressed={following}
        className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border transition-colors ${
          following
            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
            : "border-edge text-slate-400 hover:text-slate-200 hover:border-slate-500"
        } disabled:opacity-50`}
        title={following ? "Following — goal/red/HT/FT alerts on" : "Follow this match for goal alerts"}
      >
        {following ? <BellRing size={11} /> : <Bell size={11} />}
        <span>{following ? "Following" : "Follow"}</span>
      </button>
      {showIosOverlay && (
        <IosInstallOverlay onClose={() => setShowIosOverlay(false)} />
      )}
    </>
  )
}

function IosInstallOverlay({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-surface-1 border border-edge rounded-xl p-5 max-w-sm w-full shadow-e3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-2">
          <span className="text-2xl shrink-0" aria-hidden>📲</span>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold text-white">Install first — takes 5 seconds</h3>
            <p className="text-[11px] text-slate-400 leading-relaxed mt-1">
              iPhone push notifications only work for sites added to your Home Screen. Apple's rule, not ours.
            </p>
          </div>
        </div>
        <ol className="mt-4 space-y-2 text-[12px] text-slate-300">
          <li className="flex gap-2.5">
            <span className="font-bold text-emerald-400 shrink-0">1.</span>
            <span>Tap the Share button <span className="text-slate-500">(arrow-out-of-square)</span> in Safari's toolbar</span>
          </li>
          <li className="flex gap-2.5">
            <span className="font-bold text-emerald-400 shrink-0">2.</span>
            <span>Scroll down, tap <strong className="text-white">Add to Home Screen</strong></span>
          </li>
          <li className="flex gap-2.5">
            <span className="font-bold text-emerald-400 shrink-0">3.</span>
            <span>Open wc26.tinjak.com from the new icon, then tap the bell again</span>
          </li>
        </ol>
        <button
          onClick={onClose}
          className="mt-4 w-full text-[12px] font-semibold py-2 rounded-lg border border-edge text-slate-300 hover:bg-surface-3 transition-colors"
        >
          Got it
        </button>
      </div>
    </div>
  )
}
