"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader, Pagination, SectionSwitch } from "../components/ui";
import { jsonRequest } from "../lib/api";

type Collection = { id: string; name: string; url?: string; status: string; last_attempt_at: string | null;
  last_success_at: string | null; last_publication_at: string | null; last_observed_at: string | null;
  next_eligible_at: string | null; cadence_minutes: number; error_code: string | null; notice: string;
  price_date?: string | null; price_stale?: boolean; reference_date?: string | null };
type Health = { generated_at: string; scheduler: { last_seen_at: string | null; status: string }; items: Collection[]; total: number; notice: string };
const statuses: Record<string, string> = { healthy: "Collecte récente", failed: "Échec à examiner", stale: "Consultation ancienne",
  running: "En cours", interrupted: "Tentative possiblement interrompue", disabled: "Désactivée", pending: "Pas encore consultée" };
const date = (value: string | null | undefined) => value ? new Date(value).toLocaleString("fr-FR") : "Non disponible";

export default function CollectionsPage() {
  const [family, setFamily] = useState("sources"), [page, setPage] = useState(0), [revision, setRevision] = useState(0);
  const [data, setData] = useState<Health | null>(null), [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const refresh = () => jsonRequest<Health>(`/workspace/collection-health?family=${family}&limit=20&offset=${page * 20}`)
      .then(d => { if (active) { setData(d); setError(""); } }).catch(e => { if (active) setError(e.message); });
    void refresh(); const timer = setInterval(refresh, 60000);
    return () => { active = false; clearInterval(timer); };
  }, [family, page, revision]);
  return <main className="mx-auto max-w-6xl px-5 py-8 text-slate-300">
    <PageHeader title="Suivi des collectes" description="Comprenez ce qui a été récupéré, ce qui attend et pourquoi certaines données manquent." />
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <SectionSwitch value={family} onChange={v => { setFamily(v); setPage(0); setData(null); }} label="Familles de collectes"
        options={[{ value: "sources", label: "Documents et résultats" }, { value: "market", label: "Cours et calendrier" }, { value: "fx", label: "Taux de change" }]} />
      <button className="text-sm text-signal underline" onClick={() => setRevision(v => v + 1)}>Actualiser l’état</button>
    </div>
    {error && <p role="alert" className="mb-4 text-amber-300">{error}</p>}
    <p className="mb-4 rounded-xl border border-white/10 p-4 text-sm">Scheduler : {data?.scheduler.status === "recent" ? "activité observée récemment" : "activité non confirmée ou ancienne"} · Dernier contrôle : {date(data?.scheduler.last_seen_at)}. Cette activité ne garantit pas le succès de chaque collecte.</p>
    <div id="collection-results" className="grid gap-4 md:grid-cols-2">{data?.items.map(c => <article key={c.id} className="min-w-0 rounded-xl border border-white/10 bg-white/[0.02] p-5">
      <p className={`text-xs ${["failed", "stale", "interrupted"].includes(c.status) ? "text-amber-300" : "text-signal"}`}>{statuses[c.status] ?? c.status}</p>
      <h2 className="mt-2 break-words text-lg text-white">{c.name}</h2>
      <dl className="mt-4 space-y-2 text-sm">
        {[ ["Dernière tentative", date(c.last_attempt_at)], ["Dernière réussite", date(c.last_success_at)],
          ["Dernière publication datée", date(c.last_publication_at)], ["Dernière consultation conservée", date(c.last_observed_at)],
          ["Reprise / cache au plus tôt", date(c.next_eligible_at)], ["Cadence ou cache indicatif", `${c.cadence_minutes} minutes`] ].map(([k,v]) => <div key={k}><dt className="text-xs text-slate-400">{k}</dt><dd>{v}</dd></div>)}
      </dl>
      {c.price_date !== undefined && <p className={`mt-3 text-sm ${c.price_stale ? "text-amber-300" : ""}`}>Dernière séance conservée : {c.price_date ?? "aucune"}{c.price_stale ? " · cours absent ou ancien" : ""}</p>}
      {c.reference_date !== undefined && <p className="mt-3 text-sm">Date de référence : {c.reference_date ?? "aucune"}</p>}
      {c.error_code && <p className="mt-3 break-words text-sm text-amber-300">Code d’erreur : {c.error_code}</p>}
      <p className="mt-3 text-xs leading-5 text-slate-400">{c.notice}</p>
      {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm text-signal underline">Ouvrir la source ↗</a>}
    </article>)}</div>
    {!data && !error && <p>Chargement…</p>}
    {data && !data.items.length && <p className="rounded-xl border border-dashed border-white/15 p-6">Aucune tentative conservée pour cette rubrique. Les collectes dépendent des titres suivis, de leur identité et de la configuration.</p>}
    <Pagination page={page} pageSize={20} total={data?.total ?? 0} onChange={setPage} label="collectes" targetId="collection-results" />
    <p className="mt-4 text-xs leading-5 text-slate-400">{data?.notice} Une reprise passée ne signifie pas qu’une nouvelle tentative a eu lieu. Ce tableau ne consomme aucun quota fournisseur.</p>
    <Link href="/coverage" className="mt-4 inline-block text-sm text-signal underline">Examiner les données manquantes →</Link>
  </main>;
}
