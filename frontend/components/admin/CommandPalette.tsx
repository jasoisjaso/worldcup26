"use client"
/**
 * Cmd+K command palette — the keyboard-first entry point.
 *
 * Per dashboard-skill Part 5.4 (Hick's Law: fewer choices = faster decisions)
 * + Linear reference pattern (Part 1 § 3.2): every action you'd previously
 * scroll to find lives here behind a single keystroke.
 *
 * Two surface types:
 *   • Navigation — scroll to a section by name
 *   • Action — fire a state-changing operation (destructive ones gate via
 *     ConfirmDialog with typed confirmation per anti-pattern #6)
 *
 * Opens on ⌘K (mac) / Ctrl+K (everywhere else). Closes on Escape, click-out,
 * or after firing an action.
 */
import { useEffect, useState, useCallback } from "react"
import { Command } from "cmdk"

export interface PaletteCommand {
  id: string
  label: string
  hint?: string
  kind: "nav" | "action"
  /** Destructive actions must set this — triggers a typed-confirm before run. */
  destructive?: boolean
  /** For destructive — what the operator has to type. */
  confirmWord?: string
  run: () => void | Promise<void>
}

export interface CommandPaletteProps {
  commands: PaletteCommand[]
}

export function CommandPalette({ commands }: CommandPaletteProps) {
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState<PaletteCommand | null>(null)
  const [typed, setTyped] = useState("")
  const [busy, setBusy] = useState(false)

  // ⌘K / Ctrl+K toggles the palette. Universally trapped — no need for
  // operators to remember a custom shortcut.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen((v) => !v)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const fire = useCallback(async (cmd: PaletteCommand) => {
    if (cmd.destructive) {
      setConfirm(cmd)
      setTyped("")
      return
    }
    setOpen(false)
    await cmd.run()
  }, [])

  const confirmAndRun = useCallback(async () => {
    if (!confirm) return
    setBusy(true)
    try {
      await confirm.run()
    } finally {
      setBusy(false)
      setConfirm(null)
      setTyped("")
      setOpen(false)
    }
  }, [confirm])

  const navCommands = commands.filter((c) => c.kind === "nav")
  const actionCommands = commands.filter((c) => c.kind === "action")

  return (
    <>
      {/* Discoverability hint — bottom-right pill on desktop, hidden on touch.
          Operators forget the keybinding; a persistent reminder costs almost
          nothing. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-40 hidden sm:flex items-center gap-1.5 px-3 py-2 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-200 text-[11px] font-mono hover:bg-amber-500/20 transition-colors shadow-lg"
        aria-label="Open command palette"
      >
        <kbd className="px-1.5 py-0.5 rounded bg-black/30 text-[9px] tabular-nums">⌘K</kbd>
        <span>command</span>
      </button>

      {/* Mobile floating action button — same role, finger-friendly. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-40 sm:hidden w-14 h-14 rounded-full bg-amber-500 text-amber-950 text-2xl font-black shadow-xl active:scale-95 transition-transform flex items-center justify-center"
        aria-label="Open command palette"
      >
        ⌘
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start justify-center pt-[10vh] px-4"
          onClick={(e) => { if (e.target === e.currentTarget) setOpen(false) }}
          role="dialog"
          aria-modal="true"
          aria-label="Command palette"
        >
          <Command
            className="w-full max-w-lg rounded-xl border border-edge bg-surface-2 shadow-2xl overflow-hidden"
            label="Command Menu"
          >
            <div className="px-3 py-2 border-b border-edge/40 flex items-center gap-2">
              <span className="text-slate-500 text-sm">›</span>
              <Command.Input
                placeholder="Search actions, jump to a section…"
                className="flex-1 bg-transparent text-[14px] text-white placeholder:text-slate-600 focus:outline-none py-1"
                autoFocus
              />
              <kbd className="text-[9px] font-mono text-slate-600 border border-edge px-1 py-0.5 rounded">ESC</kbd>
            </div>
            <Command.List className="max-h-[60vh] overflow-y-auto p-2">
              <Command.Empty className="text-[11px] text-slate-600 px-2 py-4 text-center">
                No matching commands.
              </Command.Empty>
              {navCommands.length > 0 && (
                <Command.Group heading="Jump to" className="text-[9px] uppercase tracking-widest text-slate-500 px-2 pt-1 pb-0.5">
                  {navCommands.map((cmd) => (
                    <PaletteRow key={cmd.id} cmd={cmd} onSelect={() => fire(cmd)} />
                  ))}
                </Command.Group>
              )}
              {actionCommands.length > 0 && (
                <Command.Group heading="Actions" className="text-[9px] uppercase tracking-widest text-slate-500 px-2 pt-3 pb-0.5">
                  {actionCommands.map((cmd) => (
                    <PaletteRow key={cmd.id} cmd={cmd} onSelect={() => fire(cmd)} />
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </div>
      )}

      {/* Typed-confirmation modal — anti-pattern #6 fix. Operator must literally
          type the word (e.g. "PAUSE") before the destructive action fires. */}
      {confirm && (
        <div
          className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-sm flex items-center justify-center px-4"
          onClick={(e) => { if (e.target === e.currentTarget && !busy) setConfirm(null) }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-title"
        >
          <div className="w-full max-w-sm rounded-xl border border-rose-500/40 bg-surface-2 shadow-2xl p-5">
            <p id="confirm-title" className="text-[10px] font-bold uppercase tracking-widest text-rose-300 mb-2">Confirm destructive action</p>
            <p className="text-[14px] font-bold text-white mb-1">{confirm.label}</p>
            {confirm.hint && <p className="text-[12px] text-slate-400 mb-3">{confirm.hint}</p>}
            <label className="block text-[11px] text-slate-400 mb-1.5">
              Type <span className="font-mono font-bold text-rose-300">{confirm.confirmWord ?? confirm.label.toUpperCase()}</span> to confirm:
            </label>
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              autoCapitalize="characters"
              className="w-full px-3 py-2 rounded-md bg-surface-1 border border-edge text-white font-mono text-sm focus:outline-none focus:border-rose-500/60"
              onKeyDown={(e) => { if (e.key === "Escape" && !busy) setConfirm(null) }}
            />
            <div className="flex items-center gap-2 mt-4">
              <button
                type="button"
                onClick={() => setConfirm(null)}
                disabled={busy}
                className="flex-1 px-3 py-2 rounded-md border border-edge text-slate-300 text-[12px] hover:bg-surface-1 disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmAndRun}
                disabled={busy || typed.trim().toUpperCase() !== (confirm.confirmWord ?? confirm.label.toUpperCase())}
                className="flex-1 px-3 py-2 rounded-md bg-rose-500 text-rose-950 text-[12px] font-bold disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {busy ? "Running…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function PaletteRow({ cmd, onSelect }: { cmd: PaletteCommand; onSelect: () => void }) {
  return (
    <Command.Item
      value={`${cmd.label} ${cmd.hint ?? ""}`}
      onSelect={onSelect}
      className="flex items-center gap-3 px-2 py-2 rounded-md cursor-pointer text-[13px] text-slate-200 aria-selected:bg-surface-1 aria-selected:text-white"
    >
      <span className={`w-1.5 h-1.5 rounded-full ${cmd.destructive ? "bg-rose-400" : cmd.kind === "action" ? "bg-amber-400" : "bg-emerald-400"}`} />
      <span className="flex-1 truncate">{cmd.label}</span>
      {cmd.hint && <span className="text-[10px] text-slate-500 truncate hidden sm:inline">{cmd.hint}</span>}
      {cmd.destructive && <span className="text-[9px] font-bold uppercase tracking-widest text-rose-400 border border-rose-500/40 px-1 py-0.5 rounded">destructive</span>}
    </Command.Item>
  )
}
