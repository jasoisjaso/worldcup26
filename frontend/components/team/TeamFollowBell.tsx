"use client"

import { useCallback, useEffect, useState } from "react"
import { Bell, BellRing } from "lucide-react"
import {
  ensureSubscribed, getCachedEndpoint, iosInstallRequired, isLikelyEUiOS, pushSupported,
} from "@/lib/push"

interface TeamFollowBellProps {
  teamCode: string
  teamName: string
}

/** Per-team follow toggle for the team page hero. Same flow as the
 *  per-match FollowBell — follows EVERY upcoming fixture of this team
 *  on the backend (FollowedTeam row), so users opting into a country
 *  during a tournament get every game's goals / cards / lineups without
 *  per-match clicks.
 */
export function TeamFollowBell({ teamCode, teamName }: TeamFollowBellProps) {
  const [following, setFollowing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showIosOverlay, setShowIosOverlay] = useState(false)
  const [available, setAvailable] = useState<boolean | "eu-ios">(false)

  useEffect(() => {
    if (!pushSupported()) { setAvailable(false); return }
    if (isLikelyEUiOS()) { setAvailable("eu-ios"); return }
    setAvailable(true)
    const ep = getCachedEndpoint()
    if (!ep) return
    fetch(`/api/push/follows?endpoint=${encodeURIComponent(ep)}`, { cache: "no-store" })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return
        if ((d.teams as Array<{ team_code: string }>).some(t => t.team_code === teamCode)) {
          setFollowing(true)
        }
      })
      .catch(() => {})
  }, [teamCode])

  const toggle = useCallback(async () => {
    if (busy || available !== true) return
    setBusy(true)
    try {
      if (iosInstallRequired()) { setShowIosOverlay(true); return }
      const ep = await ensureSubscribed()
      if (!ep) return
      const path = following ? "/api/push/unfollow-team" : "/api/push/follow-team"
      const r = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: ep, team_code: teamCode }),
      })
      if (r.ok) setFollowing(!following)
    } finally {
      setBusy(false)
    }
  }, [busy, available, following, teamCode])

  if (available === false) return null
  if (available === "eu-ios") {
    return (
      <span className="text-slate-700 cursor-not-allowed" title="Web Push unavailable on iPhone in the EU (Apple DMA).">
        <Bell size={16} />
      </span>
    )
  }
  return (
    <>
      <button
        onClick={toggle}
        disabled={busy}
        aria-label={following ? `Unfollow ${teamName}` : `Follow ${teamName}`}
        aria-pressed={following}
        className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-colors ${
          following
            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/15"
            : "border-edge text-slate-400 hover:text-slate-200 hover:border-slate-500"
        } disabled:opacity-50`}
        title={
          following
            ? `Following ${teamName} — alerts on every match`
            : `Follow ${teamName} for goal & match alerts`
        }
      >
        {following ? <BellRing size={12} /> : <Bell size={12} />}
        <span>{following ? "Following" : "Follow"}</span>
      </button>
      {showIosOverlay && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-4" onClick={() => setShowIosOverlay(false)}>
          <div className="bg-surface-1 border border-edge rounded-xl p-5 max-w-sm w-full shadow-e3" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-bold text-white">Install first — takes 5 seconds</h3>
            <p className="text-[11px] text-slate-400 leading-relaxed mt-1">
              iPhone push notifications only work for sites added to your Home Screen.
            </p>
            <ol className="mt-3 space-y-1.5 text-[12px] text-slate-300 list-decimal list-inside">
              <li>Tap Share in Safari&apos;s toolbar</li>
              <li>Scroll, tap <strong className="text-white">Add to Home Screen</strong></li>
              <li>Open the new icon, tap Follow again</li>
            </ol>
            <button
              onClick={() => setShowIosOverlay(false)}
              className="mt-4 w-full text-[12px] font-semibold py-2 rounded-lg border border-edge text-slate-300 hover:bg-surface-3"
            >
              Got it
            </button>
          </div>
        </div>
      )}
    </>
  )
}
