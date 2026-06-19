"use client"
import { useEffect, useState } from "react"

const NUDGE_STATE_KEY = "wc26_install_nudge_state"
const VISIT_COUNT_KEY = "wc26_visit_count"

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>
}

type NudgeState = "hidden" | "show" | "dismissed" | "installed"

/** One-time install prompt for our PWA. Surfaces only on a user's 2nd+ visit
 * (so first-time browsers aren't ambushed), only on browsers that support
 * beforeinstallprompt (Chromium / Edge), and never again after dismissal. */
export function InstallNudge() {
  const [event, setEvent] = useState<BeforeInstallPromptEvent | null>(null)
  const [state, setState] = useState<NudgeState>("hidden")

  useEffect(() => {
    // Track visit count to gate the prompt — never on first visit, that's hostile.
    const count = parseInt(localStorage.getItem(VISIT_COUNT_KEY) || "0", 10) + 1
    localStorage.setItem(VISIT_COUNT_KEY, String(count))

    const persisted = (localStorage.getItem(NUDGE_STATE_KEY) || "hidden") as NudgeState
    if (persisted === "dismissed" || persisted === "installed") {
      setState(persisted)
      return
    }

    const onBeforeInstall = (e: Event) => {
      e.preventDefault()
      setEvent(e as BeforeInstallPromptEvent)
      // Only show on 2nd+ visit AND after a 6-second beat so it doesn't blot
      // out content on initial render.
      if (count >= 2) {
        setTimeout(() => setState("show"), 6000)
      }
    }
    const onInstalled = () => {
      setState("installed")
      localStorage.setItem(NUDGE_STATE_KEY, "installed")
    }

    window.addEventListener("beforeinstallprompt", onBeforeInstall)
    window.addEventListener("appinstalled", onInstalled)
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall)
      window.removeEventListener("appinstalled", onInstalled)
    }
  }, [])

  const accept = async () => {
    if (!event) return
    await event.prompt()
    const choice = await event.userChoice
    if (choice.outcome === "accepted") {
      setState("installed")
      localStorage.setItem(NUDGE_STATE_KEY, "installed")
    } else {
      setState("dismissed")
      localStorage.setItem(NUDGE_STATE_KEY, "dismissed")
    }
    setEvent(null)
  }

  const dismiss = () => {
    setState("dismissed")
    localStorage.setItem(NUDGE_STATE_KEY, "dismissed")
  }

  if (state !== "show" || !event) return null

  return (
    <div className="fixed top-16 left-3 right-3 sm:left-auto sm:right-4 sm:max-w-sm z-40 rounded-xl border border-emerald-500/30 bg-surface-1/95 backdrop-blur shadow-lg p-3.5 animate-in fade-in slide-in-from-top-4">
      <div className="flex items-start gap-3">
        <span className="text-lg shrink-0" aria-hidden="true">📲</span>
        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-bold text-white">Install for instant access</p>
          <p className="text-[11px] text-slate-400 leading-snug mt-0.5">
            Add WC26 to your home screen. Opens like an app, no browser bar, push alerts arrive instantly.
          </p>
        </div>
        <button
          onClick={dismiss}
          className="text-slate-500 hover:text-slate-300 text-[16px] leading-none -mt-1 -mr-1 px-1.5"
          aria-label="Dismiss"
        >×</button>
      </div>
      <div className="flex gap-2 mt-3">
        <button
          onClick={accept}
          className="flex-1 text-[11px] font-bold px-3 py-2 rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 transition-colors"
        >
          Install
        </button>
        <button
          onClick={dismiss}
          className="text-[11px] px-3 py-2 rounded-lg text-slate-500 hover:text-slate-300"
        >
          Not now
        </button>
      </div>
    </div>
  )
}
