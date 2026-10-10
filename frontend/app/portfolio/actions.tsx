"use client";

import { apiFetch } from "../lib/api";

import { Pagination, usePagination } from "../components/ui";
import { useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
const input = "w-full rounded-lg border border-white/15 bg-slate-950 p-2 text-sm text-white";
type Action = { id: string; symbol: string; exchange: string; kind: string; effective_date: string;
  quantity_entitled: number; quantity_after?: number; cash_delta: string;
  request: { source_url: string; published_at: string; note: string }; observed_at: string };

export function PortfolioActions({ portfolioId, instruments, onChange }: {
  portfolioId: string; instruments: Array<{ id: string; symbol: string; exchange: string; currency: string }>;
  onChange: () => Promise<void>;
}) {
  const [actions, setActions] = useState<Action[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState("dividend");
  const [instrument, setInstrument] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch(`${api}/market/portfolios/${portfolioId}/actions`, { cache: "no-store", signal: controller.signal })
      .then(async r => { if (!r.ok) throw new Error("Opérations sur titres indisponibles."); return r.json(); })
      .then(d => setActions(d.items)).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [portfolioId, revision]);
  const paged = usePagination(actions, 10, portfolioId);
  return <details className="mt-5 rounded-xl border border-white/10 p-4">
    <summary className="cursor-pointer text-lg text-white">Dividendes et divisions d’actions</summary>
    <p className="mt-3 text-xs leading-5 text-slate-400">Saisie sourcée propre à cette simulation. Le dividende crédite un montant net par titre détenu avant le jour UTC du détachement, sans réinvestissement. Le split change la quantité et conserve le coût total. Une fraction de titre, un split rétroactif après une opération ou une convention ambiguë bloque l’application.</p>
    <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={async e => {
      e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
      setBusy(true); setError(""); setNotice("");
      const i = instruments.find(v => v.id === instrument);
      const body = { kind, effective_date: f.get("effective_date"), source_url: f.get("source_url"),
        published_at: new Date(String(f.get("published_at"))).toISOString(), note: f.get("note"), confirmed: true,
        ...(kind === "dividend" ? { payment_date: f.get("payment_date"), currency: i?.currency,
          net_amount_per_security: f.get("amount") } : { numerator: Number(f.get("numerator")), denominator: Number(f.get("denominator")) }) };
      try { const r = await apiFetch(`${api}/market/portfolios/${portfolioId}/actions/${instrument}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        const d = await r.json(); if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Vérifie les données et dates.");
        setNotice(d.inserted ? "Opération enregistrée, portefeuille actualisé." : "Opération déjà enregistrée, aucun doublon.");
        setRevision(v => v + 1); await onChange();
      } catch (e) { setError(e instanceof Error ? e.message : "Erreur."); } finally { setBusy(false); }
    }}>
      <label className="text-xs">Titre<select aria-label="Titre" className={input} value={instrument} onChange={e => setInstrument(e.target.value)} required><option value="">Choisir</option>{instruments.map(i => <option key={i.id} value={i.id}>{i.symbol} · {i.exchange} · {i.currency}</option>)}</select></label>
      <label className="text-xs">Opération<select aria-label="Opération" className={input} value={kind} onChange={e => setKind(e.target.value)}><option value="dividend">Dividende net payé</option><option value="split">Division / regroupement</option></select></label>
      <label className="text-xs">{kind === "dividend" ? "Date de détachement" : "Date effective"}<input name="effective_date" type="date" className={input} required /></label>
      {kind === "dividend" ? <><label className="text-xs">Date du paiement<input name="payment_date" type="date" className={input} required /></label><label className="text-xs">Montant NET par titre en {instruments.find(i => i.id === instrument)?.currency ?? "devise principale"}<input name="amount" type="number" min="0.000001" max="999999" step="0.000001" className={input} required /></label></> : <><label className="text-xs">Nombre de titres nouveaux<input name="numerator" type="number" min="1" max="10000" step="1" className={input} required /></label><label className="text-xs">Pour ce nombre de titres anciens<input name="denominator" type="number" min="1" max="10000" step="1" className={input} required /></label></>}
      <label className="text-xs">URL de la publication<input name="source_url" type="url" className={input} required /></label>
      <label className="text-xs">Publication (heure locale)<input name="published_at" type="datetime-local" className={input} required /></label>
      <label className="text-xs sm:col-span-2">Preuve de la cotation, montant net / ratio et conventions<textarea name="note" className={input} required minLength={20} maxLength={1500} /></label>
      <label className="text-xs sm:col-span-2"><input type="checkbox" required /> Je confirme les données pour ce titre. Cette déclaration ne certifie pas les règles Bloomberg.</label>
      <button disabled={busy} className="rounded-lg bg-signal p-2 text-sm font-semibold text-slate-950 disabled:opacity-40">Appliquer à la simulation</button>
    </form>
    {error && <p role="alert" className="mt-3 text-amber-300">{error}</p>}{notice && <p role="status" className="mt-3 text-signal">{notice}</p>}
    <ul id="corporate-actions" className="mt-4 space-y-3 text-sm">{paged.items.map(a => <li key={a.id} className="border-t border-white/10 pt-2">{a.symbol} · {a.exchange} · {a.kind === "dividend" ? `Dividende : ${a.cash_delta} USD pour ${a.quantity_entitled} titres` : `Split : ${a.quantity_entitled} → ${a.quantity_after} titres`} · {a.effective_date}<a href={a.request.source_url} target="_blank" rel="noreferrer" className="block text-xs underline">Publication du {new Date(a.request.published_at).toLocaleString("fr-FR")}</a></li>)}</ul>
    <Pagination page={paged.page} pageSize={10} total={paged.total} onChange={paged.onChange} label="opérations sur titres" targetId="corporate-actions" />
    {!actions.length && <p className="mt-3 text-xs text-slate-500">Aucune opération sur titres enregistrée.</p>}
  </details>;
}
