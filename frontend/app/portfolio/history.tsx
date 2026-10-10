"use client";

import { apiFetch } from "../lib/api";

import { Pagination, usePagination } from "../components/ui";
import { useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
type Point = { id: string; date: string; observed_at: string; status: string;
  total_value: string | null; return_pct: string | null; cash: string;
  positions: Array<{ symbol: string; exchange: string; quantity: number; source_url: string | null;
    quote_date: string | null; usd_valuation: { conversion: { fx_source_url: string | null; fx_date: string | null } | null } }> };
type History = { items: Point[]; notice: string; limited: boolean };
const dollars = (v: string | null) => v === null ? "Indisponible" : new Intl.NumberFormat("fr-FR", { style: "currency", currency: "USD" }).format(Number(v));

export function PortfolioHistory({ portfolioId, revision }: { portfolioId: string; revision: string }) {
  const [data, setData] = useState<History | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch(`${api}/market/portfolios/${portfolioId}/history`, { cache: "no-store", signal: controller.signal })
      .then(async r => { if (!r.ok) throw new Error("Historique indisponible."); return r.json(); })
      .then((d: History) => { setData(d); setError(""); })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [portfolioId, refresh, revision]);
  const points = data?.items ?? [];
  const paged = usePagination(points.slice().reverse(), 10, portfolioId);
  const valid = points.filter(p => p.status === "available" && p.return_pct !== null);
  const values = valid.map(p => Number(p.return_pct));
  const min = Math.min(0, ...values) - 0.5, max = Math.max(0, ...values) + 0.5;
  const first = points.length ? Date.parse(points[0].date) : 0;
  const last = points.length ? Date.parse(points[points.length - 1].date) : 1;
  const x = (p: Point) => 55 + 700 * (Date.parse(p.date) - first) / Math.max(86400000, last - first);
  const y = (v: number) => 190 - 160 * (v - min) / (max - min);
  let previous: Point | null = null;
  const segments: string[] = [];
  for (const p of points) {
    if (p.status !== "available" || p.return_pct === null) { previous = null; continue; }
    if (previous && Date.parse(p.date) - Date.parse(previous.date) === 86400000)
      segments.push(`${x(previous)},${y(Number(previous.return_pct))} ${x(p)},${y(Number(p.return_pct))}`);
    previous = p;
  }
  return <section className="mt-6 rounded-xl border border-white/10 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg text-white">Historique de la simulation</h3>
      <button disabled={busy} className="text-sm text-signal underline disabled:opacity-40" onClick={async () => {
        setBusy(true); setError("");
        try { const r = await apiFetch(`${api}/market/portfolios/${portfolioId}/history`, { method: "POST" });
          if (!r.ok) throw new Error("Enregistrement impossible."); setRefresh(v => v + 1);
        } catch (e) { setError(e instanceof Error ? e.message : "Erreur."); } finally { setBusy(false); }
      }}>Enregistrer un instantané maintenant</button></div>
    <p className="mt-2 text-xs leading-5 text-slate-400">{data?.notice ?? "Chargement de l’historique…"} Enregistrement automatique chaque heure et après chaque opération.</p>
    {error && <p role="alert" className="mt-2 text-amber-300">{error}</p>}
    {valid.length > 0 ? <svg viewBox="0 0 800 235" role="img" aria-label="Performance observée par rapport au capital initial, en pourcentage" className="mt-4 w-full">
      <line x1="55" x2="755" y1={y(0)} y2={y(0)} stroke="#475569" strokeDasharray="4 4" />
      <text x="5" y={y(0) - 5} fill="#94a3b8" fontSize="12">0 %</text>
      <text x="5" y="25" fill="#94a3b8" fontSize="12">{max.toFixed(2)} %</text>
      <text x="5" y="200" fill="#94a3b8" fontSize="12">{min.toFixed(2)} %</text>
      {segments.map((s, i) => <polyline key={i} points={s} fill="none" stroke="#c7ff00" strokeWidth="2" />)}
      {valid.map(p => <circle key={p.id} cx={x(p)} cy={y(Number(p.return_pct))} r="4" fill="#c7ff00"><title>{p.date} : {p.return_pct} % · {dollars(p.total_value)}</title></circle>)}
      <text x="55" y="225" fill="#94a3b8" fontSize="12">{points[0]?.date}</text>
      <text x="755" y="225" textAnchor="end" fill="#94a3b8" fontSize="12">{points[points.length - 1]?.date}</text>
    </svg> : <p className="mt-4 text-sm">Aucun instantané complet et récent à tracer.</p>}
    {valid.length === 1 && <p className="text-xs text-slate-400">Un seul jour observé : la courbe se construira avec les prochains jours.</p>}
    <details id="daily-evidence" className="mt-3 text-sm"><summary className="cursor-pointer text-signal">Valeurs et preuves quotidiennes ({points.length})</summary>
      <ul className="mt-2 space-y-3">{paged.items.map(p => <li key={p.id} className="border-t border-white/10 pt-2">
        {p.date} · {dollars(p.total_value)} · {p.status === "available" ? `${p.return_pct} %` : p.status === "stale" ? "Données anciennes, exclu de la courbe" : "Valorisation incomplète"}
        <span className="block text-xs text-slate-500">Observé le {new Date(p.observed_at).toLocaleString("fr-FR")}</span>
        {p.positions.map((h, i) => <span key={i} className="block text-xs">{h.quantity} {h.symbol} · {h.exchange} · {h.source_url && <a className="underline" href={h.source_url} target="_blank" rel="noreferrer">cours du {h.quote_date}</a>}
          {h.usd_valuation.conversion?.fx_source_url && <> · <a className="underline" href={h.usd_valuation.conversion.fx_source_url} target="_blank" rel="noreferrer">taux du {h.usd_valuation.conversion.fx_date}</a></>}</span>)}
      </li>)}</ul><Pagination page={paged.page} pageSize={10} total={paged.total} onChange={paged.onChange} label="jours observés" targetId="daily-evidence" /></details>
    {data?.limited && <p className="text-xs text-amber-300">Affichage limité aux 365 derniers jours observés ; historique complet conservé.</p>}
  </section>;
}
