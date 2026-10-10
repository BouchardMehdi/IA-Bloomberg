"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { PageHeader, Pagination } from "../components/ui";
import { useAccess } from "../components/access-provider";
import { jsonRequest } from "../lib/api";

type Evidence = { url: string; published_at: string; note: string };
type Content = { title: string; hypothesis: string; risks: string; invalidation: string; horizon: string;
  review_on: string; status: string; observations: string; evidence: Evidence[]; trade_id: string | null; acknowledged: boolean };
type Revision = Content & { id: string; version: number; author: string; recorded_at: string };
type Decision = { id: string; instrument_id: string; portfolio_id: string | null; symbol: string; exchange: string; latest: Revision };
type Detail = { id: string; instrument_id: string; portfolio_id: string | null; items: Revision[]; next_offset: number | null; notice: string };
type Instrument = { id: string; symbol: string; exchange: string };
type Portfolio = { id: string; name: string };
type Trade = { id: string; instrument_id: string; side: string; quantity: number; executed_at: string };
const statuses: Record<string, string> = { watching: "À surveiller", considering: "En réflexion", held: "Suivi d’une position (déclaré)", closed: "Dossier clos", invalidated: "Hypothèse invalidée" };
const empty = (): Content => ({ title: "", hypothesis: "", risks: "", invalidation: "", horizon: "", review_on: new Date().toISOString().slice(0,10),
  status: "watching", observations: "", evidence: [{ url: "", published_at: "", note: "" }], trade_id: null, acknowledged: false });
const field = "mt-2 w-full rounded-lg border border-white/15 bg-slate-950 p-3 text-sm";
const localTime = (value: string) => { const d = new Date(value); return new Date(d.getTime() - d.getTimezoneOffset()*60000).toISOString().slice(0,16); };

export default function JournalPage() {
  const access = useAccess(), canWrite = access.user?.role !== "viewer";
  const [instruments,setInstruments] = useState<Instrument[]>([]), [portfolios,setPortfolios] = useState<Portfolio[]>([]);
  const [data,setData] = useState<{ items: Decision[]; total: number; notice: string } | null>(null);
  const [status,setStatus] = useState(""), [page,setPage] = useState(0), [revision,setRevision] = useState(0);
  const [selected,setSelected] = useState(""), [detail,setDetail] = useState<Detail | null>(null), [historyPage,setHistoryPage] = useState(0);
  const [editing,setEditing] = useState(false), [form,setForm] = useState<Content>(empty), [instrument,setInstrument] = useState(""), [portfolio,setPortfolio] = useState("");
  const [expectedVersion,setExpectedVersion] = useState(0), [trades,setTrades] = useState<Trade[]>([]);
  const [error,setError] = useState(""), [notice,setNotice] = useState(""), [busy,setBusy] = useState(false);
  const submission = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => {
    let active=true;
    Promise.all([jsonRequest<{ items: Instrument[] }>("/market/instruments"),jsonRequest<{ items: Portfolio[] }>("/market/portfolios")])
      .then(([i,p]) => { if(active) { setInstruments(i.items); setPortfolios(p.items); setSelected(current=>current || new URLSearchParams(window.location.search).get("decision") || ""); } }).catch(e => { if(active) setError(e.message); });
    return () => { active=false; };
  }, []);
  useEffect(() => { let active=true; jsonRequest<{ items: Decision[]; total: number; notice: string }>(`/workspace/journal?limit=20&offset=${page*20}${status ? `&status=${status}` : ""}`)
    .then(d => { if(active) setData(d); }).catch(e => { if(active) setError(e.message); }); return () => { active=false; }; }, [page,status,revision]);
  useEffect(() => {
    if(!selected) return;
    let active=true;
    jsonRequest<Detail>(`/workspace/journal/${selected}?limit=10&offset=${historyPage*10}`)
      .then(d => { if(active) setDetail(d); }).catch(e => { if(active) setError(e.message); });
    return () => { active=false; };
  }, [selected,historyPage,revision]);
  useEffect(() => {
    if(!portfolio) return;
    let active=true;
    jsonRequest<{ trades: Trade[] }>(`/market/portfolios/${portfolio}`).then(d => { if(active) setTrades(d.trades); }).catch(e => { if(active) setError(e.message); });
    return () => { active=false; };
  }, [portfolio]);
  function create() { setSelected(""); setDetail(null); setExpectedVersion(0); setEditing(true); setForm(empty()); setInstrument(""); setPortfolio(""); setTrades([]); setError(""); setNotice(""); submission.current=null; }
  function revise() {
    if(!detail?.items.length || historyPage) return;
    const r=detail.items[0];
    setForm({title:r.title,hypothesis:r.hypothesis,risks:r.risks,invalidation:r.invalidation,horizon:r.horizon,review_on:r.review_on,
      status:r.status,observations:r.observations,evidence:r.evidence.map(e=>({...e,published_at:localTime(e.published_at)})),trade_id:r.trade_id,acknowledged:false});
    setInstrument(detail.instrument_id); setPortfolio(detail.portfolio_id ?? ""); setTrades([]); setExpectedVersion(r.version); setEditing(true); setError(""); submission.current=null;
  }
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const payload={...form,evidence:form.evidence.map(p=>({...p,published_at:new Date(p.published_at).toISOString()})),
        ...(expectedVersion ? {expected_version:expectedVersion} : {instrument_id:instrument,portfolio_id:portfolio || null})};
      const fingerprint=JSON.stringify(payload);
      if(submission.current?.fingerprint !== fingerprint) submission.current={fingerprint,key:crypto.randomUUID()};
      const result=await jsonRequest<{decision_id:string}>(expectedVersion ? `/workspace/journal/${selected}/revisions` : "/workspace/journal",{...payload,client_request_id:submission.current.key});
      setSelected(result.decision_id); setHistoryPage(0); setEditing(false); setRevision(v=>v+1); setNotice("Révision enregistrée. L’historique précédent est conservé."); submission.current=null;
    } catch(e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <main className="mx-auto max-w-6xl px-5 py-8 text-slate-300">
    <PageHeader title="Journal des décisions" description="Écrivez votre hypothèse, ses risques et les raisons de la réexaminer. Retrouvez ensuite ce que vous saviez au moment de chaque révision." />
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4"><label className="text-sm">Filtrer les dossiers<select className={field} value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="">Tous les statuts</option>{Object.entries(statuses).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>{canWrite && <button className="rounded-lg border border-signal/40 px-4 py-3 text-sm text-signal" onClick={create}>Nouvelle hypothèse</button>}</div>
    {error && <p role="alert" className="mb-4 text-amber-300">{error}</p>}{notice && <p role="status" className="mb-4 text-signal">{notice}</p>}
    <p className="mb-4 text-xs leading-5 text-slate-400">{data?.notice} Le statut « suivi d’une position » est une déclaration, pas une preuve de détention. Les décisions passées ne peuvent pas être antidatées.</p>
    <div id="journal-results" className="grid gap-3 md:grid-cols-2">{data?.items.map(d=><article key={d.id} className="rounded-xl border border-white/10 p-5"><p className="text-xs text-signal">{d.symbol} · {d.exchange} · {statuses[d.latest.status]}</p><h2 className="mt-2 break-words text-lg text-white">{d.latest.title}</h2><p className="mt-2 text-sm">Réexamen : {d.latest.review_on} · Révision {d.latest.version}</p><button className="mt-3 text-sm text-signal underline" onClick={()=>{setSelected(d.id);setHistoryPage(0);setDetail(null);setEditing(false);setError("");}}>Ouvrir le dossier</button></article>)}</div>
    {data && !data.items.length && <p className="rounded-xl border border-dashed border-white/15 p-6">Aucun dossier pour ce filtre. Commencez par une hypothèse documentée.</p>}
    <Pagination page={page} pageSize={20} total={data?.total ?? 0} onChange={setPage} label="dossiers" targetId="journal-results" />
    {selected && !editing && <section id="journal-history" className="mt-6 rounded-xl border border-white/10 p-5"><div className="mb-4 flex flex-wrap justify-between gap-3"><h2 className="text-xl text-white">Historique du dossier</h2>{canWrite && historyPage === 0 && <button disabled={!detail} className="text-sm text-signal underline" onClick={revise}>Ajouter une révision</button>}</div>{detail?.items.map(r=><article key={r.id} className="border-t border-white/10 py-5"><h3 className="break-words text-lg text-white">{r.title} · Révision {r.version}</h3><p className="mt-2 break-words text-xs text-slate-400">Enregistrée le {new Date(r.recorded_at).toLocaleString("fr-FR")} · Auteur {r.author} · {statuses[r.status]}</p><dl className="mt-4 space-y-4 text-sm">{[["Hypothèse",r.hypothesis],["Risques",r.risks],["Conditions d’invalidation",r.invalidation],["Horizon",r.horizon],["Réexamen prévu",r.review_on],["Observations de suivi",r.observations || "Aucune"]].map(([label,value])=><div key={label}><dt className="font-medium text-white">{label}</dt><dd className="mt-1 whitespace-pre-wrap break-words leading-6">{value}</dd></div>)}</dl><ul className="mt-4 space-y-3">{r.evidence.map((p,i)=><li key={i} className="break-words text-sm"><a href={p.url} target="_blank" rel="noreferrer" className="text-signal underline">Source {i+1} ↗</a><p className="mt-1 text-xs text-slate-400">Publication : {new Date(p.published_at).toLocaleString("fr-FR")}</p><p className="mt-1">{p.note}</p></li>)}</ul>{r.trade_id && <p className="mt-3 break-all text-xs text-slate-400">Opération simulée référencée : {r.trade_id}. Aucune opération créée par ce dossier.</p>}</article>)}<Pagination page={historyPage} pageSize={10} hasNext={detail?.next_offset !== null && detail?.next_offset !== undefined} onChange={setHistoryPage} label="révisions" targetId="journal-history" /></section>}
    {editing && canWrite && <form onSubmit={save} className="mt-6 rounded-xl border border-white/10 p-5"><h2 className="mb-4 text-xl text-white">{expectedVersion ? `Nouvelle révision après la version ${expectedVersion}` : "Nouvelle hypothèse"}</h2><div className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm">Titre suivi<select required disabled={expectedVersion > 0} className={field} value={instrument} onChange={e=>{setInstrument(e.target.value);setForm({...form,trade_id:null});}}><option value="">Choisir un titre</option>{instruments.map(i=><option key={i.id} value={i.id}>{i.symbol} · {i.exchange}</option>)}</select></label>
      <label className="text-sm">Simulation (facultative)<select disabled={expectedVersion > 0} className={field} value={portfolio} onChange={e=>{setPortfolio(e.target.value);setTrades([]);setForm({...form,trade_id:null});}}><option value="">Recherche sans simulation</option>{portfolios.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label className="text-sm sm:col-span-2">Titre du dossier<input required minLength={3} maxLength={200} className={field} value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/></label>
      {([ ["hypothesis","Hypothèse à examiner",10,6000],["risks","Risques identifiés",5,4000],["invalidation","Ce qui invaliderait cette hypothèse",5,4000],["observations","Observations de suivi",0,6000] ] as const).map(([key,label,min,max])=><label key={key} className="text-sm sm:col-span-2">{label}<textarea rows={3} required={min>0} minLength={min} maxLength={max} className={field} value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}/></label>)}
      <label className="text-sm">Horizon envisagé<input required minLength={2} maxLength={200} className={field} value={form.horizon} onChange={e=>setForm({...form,horizon:e.target.value})}/></label>
      <label className="text-sm">Date de réexamen<input required type="date" className={field} value={form.review_on} onChange={e=>setForm({...form,review_on:e.target.value})}/></label>
      <label className="text-sm">Statut<select className={field} value={form.status} onChange={e=>setForm({...form,status:e.target.value})}>{Object.entries(statuses).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
      <label className="text-sm">Opération simulée de référence (facultative)<select disabled={!portfolio} className={field} value={form.trade_id ?? ""} onChange={e=>setForm({...form,trade_id:e.target.value || null})}><option value="">Aucune opération liée</option>{trades.filter(t=>t.instrument_id===instrument).map(t=><option key={t.id} value={t.id}>{t.side==="buy"?"Achat":"Vente"} · {t.quantity} · {new Date(t.executed_at).toLocaleDateString("fr-FR")}</option>)}{form.trade_id && !trades.some(t=>t.id===form.trade_id) && <option value={form.trade_id}>Référence conservée</option>}</select><span className="mt-1 block text-xs text-slate-400">Liste limitée aux opérations récentes conservées par la fiche portefeuille.</span></label>
    </div><h3 className="mb-3 mt-5 text-white">Sources documentaires</h3>{form.evidence.map((p,index)=><fieldset key={index} className="mb-4 grid min-w-0 gap-3 rounded-lg border border-white/10 p-4 sm:grid-cols-2"><legend className="px-1 text-sm">Source {index+1}</legend>{([ ["url","URL publique", "url"],["published_at","Publication (heure locale)","datetime-local"],["note","Ce que cette source documente","text"] ] as const).map(([key,label,type])=><label key={key} className={`text-sm ${key==="note"?"sm:col-span-2":""}`}>{label}<input type={type} required maxLength={key==="note"?1000:undefined} className={field} value={p[key]} onChange={e=>setForm({...form,evidence:form.evidence.map((v,i)=>i===index?{...v,[key]:e.target.value}:v)})}/></label>)}{form.evidence.length>1 && <button type="button" className="text-left text-sm text-signal underline" onClick={()=>setForm({...form,evidence:form.evidence.filter((_,i)=>i!==index)})}>Retirer cette source de la nouvelle révision</button>}</fieldset>)}
      {form.evidence.length<20 && <button type="button" className="text-sm text-signal underline" onClick={()=>setForm({...form,evidence:[...form.evidence,{url:"",published_at:"",note:""}]})}>Ajouter une source</button>}
      <label className="my-5 flex items-start gap-3 text-sm leading-6"><input required type="checkbox" checked={form.acknowledged} onChange={e=>setForm({...form,acknowledged:e.target.checked})} className="mt-1"/>Je distingue mes hypothèses des faits sourcés. La saisie ne certifie pas les preuves et ne déclenche aucun ordre.</label>
      <div className="flex flex-wrap gap-4"><button disabled={busy} className="rounded-lg border border-signal/40 px-4 py-3 text-sm text-signal">{busy?"Enregistrement…":"Enregistrer la révision"}</button><button type="button" disabled={busy} className="text-sm underline" onClick={()=>setEditing(false)}>Annuler</button></div>
    </form>}
  </main>;
}
