"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"

export default function LoginForm() {
  const router = useRouter()
  const [token, setToken] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch("/api/admin/auth", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: token.trim() }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.error ?? `Sign-in failed (${res.status})`)
        return
      }
      router.replace("/admin")
      router.refresh()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">Token</span>
        <input
          type="password"
          autoComplete="off"
          autoFocus
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className="mt-1 w-full bg-surface-2 border border-edge rounded px-3 py-2 text-slate-100 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
          placeholder="WC26_ADMIN_TOKEN"
        />
      </label>
      {error && (
        <div className="text-sm text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded px-3 py-2">
          {error}
        </div>
      )}
      <button
        type="submit"
        disabled={busy || !token.trim()}
        className="w-full bg-amber-500 text-surface-0 font-semibold rounded px-3 py-2 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-amber-400 transition"
      >
        {busy ? "Verifying…" : "Sign in"}
      </button>
    </form>
  )
}
