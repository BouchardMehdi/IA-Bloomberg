"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader, Pagination } from "../components/ui";
import { jsonRequest } from "../lib/api";
import { useAccess } from "../components/access-provider";

type Alert = { id: string; kind: string; title: string; message: string; read: boolean;
  created_at: string; published_at: string | null; url: string | null; page: string };
type Alerts = { items: Alert[]; total: number; unread_count: number; notice: string };
const labels: Record<string, string> = { publication: "Publication", extracted_fact: "Fait extrait", calendar: "Calendrier", collection_error: "Problème de collecte" };

export default function AlertsPage() {
  const [kind, setKind] = useState("");
  const [unread, setUnread] = useState(false);
  const [page, setPage] = useState(0);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Alerts | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const access = useAccess();
  useEffect(() => {
    let active = true;
    jsonRequest<Alerts>(`/workspace/alerts?limit=20&offset=${page * 20}&unread=${unread}${kind ? `&kind=${kind}` : ""}`)
      .then(d => { if (active) { setData(d); setError(""); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [kind, unread, page, revision]);
  async function act(path: string) {
    setBusy(true); setError("");
    try { await jsonRequest(path, {}); setRevision(v => v + 1); window.dispatchEvent(new Event("market-ai:alerts-changed")); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <main className="mx-auto max-w-6xl px-5 py-8 text-slate-300">
    <PageHeader title="Mes alertes" description="Retrouvez les nouvelles observations et les problèmes de collecte, sans devoir parcourir chaque page." />
    <div className="mb-5 flex flex-wrap items-center gap-4">
      <label className="text-sm">Type<select className="ml-2 rounded-lg border border-white/15 bg-slate-950 p-2" value={kind} onChange={e => { setKind(e.target.value); setPage(0); }}><option value="">Toutes les alertes</option>{Object.entries(labels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={unread} onChange={e => { setUnread(e.target.checked); setPage(0); }} />Non lues uniquement</label>
      <button className="text-sm text-signal underline" disabled={busy} onClick={() => setRevision(v => v + 1)}>Actualiser l’affichage</button>
      {access.user?.role !== "viewer" && <button className="text-sm text-signal underline" disabled={busy} onClick={() => act("/workspace/alerts/refresh")}>Rechercher les nouvelles alertes</button>}
    </div>
    {error && <p role="alert" className="mb-4 text-amber-300">{error}</p>}
    <p className="mb-4 text-sm">{data ? `${data.unread_count} alerte(s) non lue(s)` : "Chargement…"}</p>
    <div id="alerts-results" className="space-y-3">{data?.items.map(a => <article key={a.id} className={`rounded-xl border p-4 sm:p-5 ${a.read ? "border-white/10" : "border-signal/30 bg-signal/[0.025]"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><p className="text-xs text-signal">{labels[a.kind] ?? a.kind} · {a.read ? "Lue" : "Non lue"}</p><h2 className="mt-2 break-words text-lg text-white">{a.title}</h2></div>{!a.read && <button disabled={busy} className="rounded-lg border border-white/15 px-3 py-2 text-xs" onClick={() => act(`/workspace/alerts/${a.id}/read`)}>Marquer comme lue</button>}</div>
      <p className="mt-3 text-sm leading-6">{a.message}</p>
      <p className="mt-3 text-xs text-slate-400">Détectée le {new Date(a.created_at).toLocaleString("fr-FR")}{a.published_at ? ` · Source publiée le ${new Date(a.published_at).toLocaleString("fr-FR")}` : " · Date de publication non fournie ou alerte technique"}</p>
      <div className="mt-3 flex flex-wrap gap-4 text-sm text-signal">{a.url && <a href={a.url} target="_blank" rel="noreferrer" className="underline">Voir la source ↗</a>}<Link href={a.page} className="underline">Ouvrir la page concernée →</Link></div>
    </article>)}</div>
    {data && !data.items.length && <p className="rounded-xl border border-dashed border-white/15 p-6 text-sm">Aucune alerte pour ces filtres. Le suivi automatique vérifie les nouvelles données chaque minute.</p>}
    <Pagination page={page} pageSize={20} total={data?.total ?? 0} busy={busy} onChange={setPage} label="alertes" targetId="alerts-results" />
    <p className="mt-4 text-xs text-slate-400">{data?.notice} En mode local sans comptes, le statut de lecture est partagé.</p>
  </main>;
}
