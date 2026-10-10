"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader, Pagination, SectionSwitch, usePagination } from "../components/ui";
import { jsonRequest } from "../lib/api";

type Briefing = { day: string; generated_at: string; items: Array<{ id: string; kind: string; title: string; message: string;
  detected_at: string; published_at: string | null; url: string | null; page: string; held: boolean }>;
  total: number; counts: Record<string, number>; research: Array<{ instrument_id: string; symbol: string; observations: number; held: boolean }>;
  upcoming: Array<{ instrument_id: string; symbol: string; exchange: string; report_date: string; fiscal_period_end: string;
    source_url: string; published_at: string | null; conflicting_dates: boolean; held: boolean }>;
  financials: Array<{ id: string; cik: string; taxonomy: string; concept: string; value: string; unit: string;
    start: string | null; end: string; filed: string; source_url: string }>;
  reviews: Array<{ id: string; symbol: string; latest: { title: string; review_on: string } }>;
  limited: boolean; notice: string; holdings_notice: string };
const labels: Record<string, string> = { publication: "Publications", extracted_fact: "Faits extraits", calendar: "Calendrier", collection_error: "Erreurs techniques" };

export default function BriefingPage() {
  const [day, setDay] = useState(new Date().toISOString().slice(0,10)), [portfolio, setPortfolio] = useState("");
  const [heldOnly, setHeldOnly] = useState(false), [page, setPage] = useState(0), [section, setSection] = useState("news"), [revision, setRevision] = useState(0);
  const [portfolios, setPortfolios] = useState<Array<{ id: string; name: string }>>([]);
  const [data, setData] = useState<Briefing | null>(null), [error, setError] = useState("");
  useEffect(() => { let active = true; jsonRequest<{ items: typeof portfolios }>("/market/portfolios").then(d => { if(active) setPortfolios(d.items); }).catch(e => { if(active) setError(e.message); }); return () => { active=false; }; }, []);
  useEffect(() => {
    let active = true;
    jsonRequest<Briefing>(`/workspace/briefing?day=${day}&held_only=${heldOnly}&limit=20&offset=${page * 20}${portfolio ? `&portfolio_id=${portfolio}` : ""}`)
      .then(d => { if(active) { setData(d); setError(""); } }).catch(e => { if(active) setError(e.message); });
    return () => { active=false; };
  }, [day, portfolio, heldOnly, page, revision]);
  const upcoming = usePagination(data?.upcoming ?? [], 10, `${day}:${portfolio}:${heldOnly}`);
  const financials = usePagination(data?.financials ?? [], 10, `${day}:${portfolio}:${heldOnly}`);
  const reviews = usePagination(data?.reviews ?? [], 10, `${day}:${portfolio}:${heldOnly}`);
  return <main className="mx-auto max-w-6xl px-5 py-8 text-slate-300">
    <PageHeader title="Briefing quotidien" description="Les nouveautés à lire, les prochains résultats et les hypothèses à réexaminer, avec leurs sources." />
    <div className="mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <label className="text-sm">Journée UTC<input type="date" className="mt-2 w-full rounded-lg border border-white/15 bg-slate-950 p-3" value={day} max={new Date().toISOString().slice(0,10)} onChange={e => { setDay(e.target.value); setPage(0); setData(null); }} /></label>
      <label className="text-sm">Simulation<select className="mt-2 w-full rounded-lg border border-white/15 bg-slate-950 p-3" value={portfolio} onChange={e => { setPortfolio(e.target.value); setHeldOnly(false); setPage(0); setData(null); }}><option value="">Tous les titres suivis</option>{portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!portfolio} checked={heldOnly} onChange={e => { setHeldOnly(e.target.checked); setPage(0); setData(null); }} />Positions détenues uniquement</label>
      <button className="self-end rounded-lg border border-white/15 p-3 text-sm" onClick={() => setRevision(v => v + 1)}>Actualiser le briefing</button>
    </div>
    {error && <p role="alert" className="mb-4 text-amber-300">{error}</p>}
    <p className="mb-4 text-xs leading-5 text-slate-400">{data?.notice ?? "Chargement du briefing…"} {portfolio && data?.holdings_notice}</p>
    {data?.limited && <p className="mb-4 text-sm text-amber-300">Une borne de lecture est atteinte : ce briefing est partiel.</p>}
    <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">{Object.entries(labels).map(([key,label]) => <div key={key} className="rounded-xl border border-white/10 p-4"><p className="text-xs text-slate-400">{label}</p><p className="mt-2 text-2xl text-white">{data?.counts[key] ?? 0}</p></div>)}</div>
    <SectionSwitch value={section} onChange={setSection} label="Rubriques du briefing" options={[{ value: "news", label: "Nouveautés" }, { value: "upcoming", label: "Prochains résultats" }, { value: "financials", label: "Chiffres collectés" }, { value: "reviews", label: "À réexaminer" }]} />
    {section === "news" && <section className="mt-5" id="briefing-news"><div className="space-y-3">{data?.items.map(a => <article key={a.id} className="rounded-xl border border-white/10 p-5"><p className="text-xs text-signal">{labels[a.kind] ?? a.kind}{a.held ? " · Position détenue actuellement" : ""}</p><h2 className="mt-2 break-words text-lg text-white">{a.title}</h2><p className="mt-3 text-sm leading-6">{a.message}</p><p className="mt-3 text-xs text-slate-400">Détecté le {new Date(a.detected_at).toLocaleString("fr-FR")} · Publication : {a.published_at ? new Date(a.published_at).toLocaleString("fr-FR") : "date non fournie / alerte technique"}</p><div className="mt-3 flex flex-wrap gap-4 text-sm text-signal">{a.url && <a href={a.url} target="_blank" rel="noreferrer" className="underline">Source ↗</a>}<Link href={a.page} className="underline">Examiner →</Link></div></article>)}</div>{data && !data.items.length && <p className="p-5">Aucune nouveauté conservée pour cette journée et ces filtres. Cela ne prouve pas l’absence de nouvelles.</p>}<Pagination page={page} pageSize={20} total={data?.total ?? 0} onChange={setPage} label="observations" targetId="briefing-news" /></section>}
    {section === "upcoming" && <section id="briefing-upcoming" className="mt-5 space-y-3">{upcoming.items.map((u,i) => <article key={`${u.instrument_id}:${i}`} className="rounded-xl border border-white/10 p-5"><h2 className="text-white">{u.symbol} · {u.exchange} · {u.report_date}</h2><p className="mt-2 text-sm">Résultats prévisionnels à confirmer · période terminant le {u.fiscal_period_end}{u.held ? " · Position détenue actuellement" : ""}</p>{u.conflicting_dates && <p className="mt-2 text-amber-300">Dates contradictoires : vérifier les publications officielles.</p>}<a href={u.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm text-signal underline">Source · {u.published_at ? new Date(u.published_at).toLocaleString("fr-FR") : "publication non fournie"}</a></article>)}{!upcoming.total && <p>Aucune échéance exploitable dans les 14 jours. Les anciennes prévisions déplacées ne sont pas réactivées.</p>}<Pagination {...upcoming} label="échéances" targetId="briefing-upcoming" /></section>}
    {section === "financials" && <section id="briefing-financials" className="mt-5 space-y-3"><p className="text-sm text-slate-400">Chiffres découverts ce jour, potentiellement publiés auparavant. Observations de l’émetteur ; aucune attribution automatique à une cotation.</p>{financials.items.map(f => <article key={f.id} className="rounded-xl border border-white/10 p-5"><h2 className="break-words text-white">CIK {f.cik} · {f.taxonomy}:{f.concept}</h2><p className="mt-2">{f.value} {f.unit}</p><p className="mt-2 text-sm">{f.start ? `Du ${f.start} au ${f.end}` : `Solde au ${f.end}`} · Dépôt du {f.filed}</p><a href={f.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm text-signal underline">Dépôt source ↗</a></article>)}{!financials.total && <p>Aucune nouvelle observation chiffrée conservée ce jour.</p>}<Pagination {...financials} label="chiffres" targetId="briefing-financials" /></section>}
    {section === "reviews" && <section id="briefing-reviews" className="mt-5 space-y-3">{data?.research.map(r => <article key={r.instrument_id} className="rounded-xl border border-white/10 p-4"><h2 className="text-white">{r.symbol}</h2><p className="mt-2 text-sm">{r.observations} observation(s) à lire. Ce nombre n’est ni un score d’achat ni une mesure d’impact.</p><Link href="/analysis" className="mt-2 inline-block text-sm text-signal underline">Ouvrir les dossiers d’analyse →</Link></article>)}{reviews.items.map(r => <article key={r.id} className="rounded-xl border border-amber-300/20 p-4"><h2 className="text-white">{r.symbol} · {r.latest.title}</h2><p className="mt-2 text-sm">Réexamen prévu le {r.latest.review_on}</p><Link href={`/journal?decision=${r.id}`} className="mt-2 inline-block text-sm text-signal underline">Relire l’hypothèse →</Link></article>)}{!data?.research.length && !reviews.total && <p>Aucun dossier à réexaminer dans cette couverture.</p>}<Pagination {...reviews} label="hypothèses à revoir" targetId="briefing-reviews" /></section>}
  </main>;
}
