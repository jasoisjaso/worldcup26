import type { MarketsSheet as Sheet } from "@/lib/types"

function pct(p: number) {
  if (p >= 0.995) return "99%+"
  if (p > 0 && p < 0.005) return "<1%"
  return `${Math.round(p * 100)}%`
}

function odds(o: number | null) {
  return o == null ? "—" : o.toFixed(2)
}

export function MarketsSheet({ sheet }: { sheet: Sheet }) {
  return (
    <div>
      <div className="rounded-xl border border-emerald-500/15 bg-emerald-500/[0.04] p-3.5 mb-4">
        <p className="text-[13px] text-slate-200 font-semibold mb-1">How to use this</p>
        <p className="text-[12px] text-slate-400 leading-relaxed">
          <span className="text-emerald-400 font-semibold">Fair odds</span> is the lowest price worth
          taking — the point where a bet is break-even. If your bookmaker offers a{" "}
          <span className="text-slate-200">bigger</span> number than the fair odds here, the model
          says that&apos;s value. Shop around: the same bet is often priced differently across books.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        {sheet.groups.map((g) => (
          <div key={g.key} className="rounded-xl border border-[#16203a] bg-[#0b1018] p-3.5">
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500 mb-2.5">{g.name}</p>
            <div className="space-y-1">
              {g.outcomes.map((o) => (
                <div key={o.key} className="flex items-center gap-2 text-[12.5px]">
                  <span className="flex-1 text-slate-300 truncate">{o.label}</span>
                  <span className="font-mono tabular-nums text-slate-500 w-12 text-right">{pct(o.prob)}</span>
                  <span className="font-mono tabular-nums font-bold text-slate-100 w-14 text-right">{odds(o.fair_odds)}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <p className="text-[11px] text-slate-600 mt-4 leading-relaxed">
        Probabilities and fair odds are derived from the model&apos;s full score-line distribution
        (expected goals: home {sheet.lambda_home.toFixed(2)}, away {sheet.lambda_away.toFixed(2)}).
        Half-time and HT/FT markets use a 45/55 first-half split. These are model estimates, not a
        betting guarantee.
      </p>
    </div>
  )
}
