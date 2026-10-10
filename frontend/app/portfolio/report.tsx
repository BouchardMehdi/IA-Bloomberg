"use client";

import { useEffect, useState } from "react";
import { jsonRequest } from "../lib/api";
import { Pagination, usePagination, SectionSwitch } from "../components/ui";

type Bucket = { label: string; value_usd: string | null; weight_pct: string | null; titles: number };
type Report = { allocation: { sector: Bucket[]; country: Bucket[]; currency: Bucket[]; security: Bucket[];
  cash: { value_usd: string; weight_pct: string | null }; status: string };
  profiles: Record<string, { source_url: string; published_at: string; note: string }>;
  benchmark_series: { id: string; name: string }[]; history_limited: boolean; notice: string;
  comparison: { status: string; reason?: string; starts_on?: string; ends_on?: string; portfolio_pct?: string;
    benchmark_pct?: string; difference_pp?: string | null; convention?: string; notice?: string;
    sources?: { source_url: string; published_at: string }[] } };
const usd = (v: string | null) => v === null ? "Indisponible" : new Intl.NumberFormat("fr-FR", { style: "currency", currency: "USD" }).format(Number(v));

export function PortfolioReport({ portfolioId, revision }: { portfolioId: string; revision: string }) {
  const [data, setData] = useState<Report | null>(null);
  const [series, setSeries] = useState("");
  const [dimension, setDimension] = useState("security");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    jsonRequest<Report>(`/workspace/portfolios/${portfolioId}/report${series ? `?series=${encodeURIComponent(series)}` : ""}`)
      .then(d => { if (active) { setData(d); setError(""); } }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [portfolioId, revision, series]);
  const buckets = data?.allocation[dimension as "sector" | "country" | "currency" | "security"] ?? [];
  const paged = usePagination(buckets, 10, dimension);
  return <section className="my-6 border-t border-white/10 pt-5">
    <h3 className="text-xl text-white">Répartition et comparaison</h3>
    {error && <p role="alert" className="mt-3 text-amber-300">{error}</p>}
    {data && <>
      <p className="my-3 text-xs leading-5 text-slate-400">{data.notice}</p>
      <SectionSwitch value={dimension} onChange={setDimension} label="Répartition" options={[{ value: "security", label: "Par titre" }, { value: "sector", label: "Par secteur" }, { value: "country", label: "Par pays" }, { value: "currency", label: "Par devise" }]} />
      <p className="mb-3 text-sm">Liquidités : {usd(data.allocation.cash.value_usd)} · {data.allocation.cash.weight_pct === null ? "Poids indisponible" : `${data.allocation.cash.weight_pct} % du portefeuille`}</p>
      <ul id="allocation-results" className="space-y-3">{paged.items.map(b => <li key={b.label} className="rounded-lg border border-white/10 p-3"><div className="flex flex-wrap justify-between gap-2 text-sm"><span className="text-white">{b.label}</span><span>{usd(b.value_usd)} · {b.weight_pct === null ? "Poids indisponible" : `${b.weight_pct} %`}</span></div>{b.weight_pct !== null && <div aria-hidden="true" className="mt-2 h-1.5 rounded bg-white/5"><div className="h-full rounded bg-signal/70" style={{ width: `${Math.max(0, Math.min(100, Number(b.weight_pct)))}%` }} /></div>}</li>)}</ul>
      {!buckets.length && <p className="text-sm text-slate-400">Aucune position ouverte.</p>}
      <Pagination page={paged.page} pageSize={10} total={paged.total} onChange={paged.onChange} label="groupes" targetId="allocation-results" />
      {Object.keys(data.profiles).length > 0 && <details className="my-3 text-xs"><summary className="cursor-pointer text-signal">Sources des classifications déclarées</summary><ul className="mt-2 space-y-2">{Object.entries(data.profiles).map(([id, p]) => <li key={id}><a href={p.source_url} target="_blank" rel="noreferrer" className="underline">Source publiée le {new Date(p.published_at).toLocaleDateString("fr-FR")}</a> · {p.note}</li>)}</ul></details>}
      <label className="mt-5 block text-sm">Indice de comparaison<select className="mt-2 w-full rounded-lg border border-white/15 bg-slate-950 p-2" value={series} onChange={e => setSeries(e.target.value)}><option value="">Choisir une série sourcée</option>{data.benchmark_series.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      {!data.benchmark_series.length && <p className="mt-2 text-xs text-slate-400">Aucun historique d’indice importé. Les valeurs du WLS ne sont pas reconstituées.</p>}
      <p className="mt-3 text-sm">{data.comparison.status === "available" ? `Du ${data.comparison.starts_on} au ${data.comparison.ends_on} : portefeuille ${data.comparison.portfolio_pct} % · indice ${data.comparison.benchmark_pct} %${data.comparison.difference_pp != null ? ` · écart ${data.comparison.difference_pp} points` : " · indice de prix, dividendes exclus"}` : data.comparison.reason}</p>
      {data.comparison.sources?.map((s, i) => <a key={i} href={s.source_url} target="_blank" rel="noreferrer" className="mr-4 mt-2 inline-block text-xs text-signal underline">Source de la borne {i + 1} · {new Date(s.published_at).toLocaleDateString("fr-FR")}</a>)}
      <p className="mt-2 text-xs leading-5 text-slate-400">{data.comparison.notice}{data.history_limited && " Comparaison limitée aux 1 000 derniers jours observés."}</p>
    </>}
  </section>;
}
