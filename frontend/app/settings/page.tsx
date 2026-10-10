"use client";

import { useEffect, useState } from "react";
import { PageHeader, SectionSwitch, Pagination } from "../components/ui";
import { useAccess, type User } from "../components/access-provider";
import { jsonRequest } from "../lib/api";

type Proposal = { id: string; instrument_id: string; kind: string; effective_date: string;
  payment_date?: string; net_amount_per_security?: string; currency?: string; numerator?: number;
  denominator?: number; source_url: string; published_at: string; note: string };
const input = "mt-1 w-full rounded-lg border border-white/15 bg-slate-950 p-2.5 text-sm text-white";
const button = "rounded-lg bg-signal px-4 py-2.5 text-sm font-medium text-slate-950 disabled:opacity-40";

export default function SettingsPage() {
  const access = useAccess();
  const admin = !access.auth_enabled || access.user?.role === "admin";
  const editor = !access.auth_enabled || access.user?.role !== "viewer";
  const [section, setSection] = useState("imports");
  const [mode, setMode] = useState("data");
  const [text, setText] = useState("");
  const [instrumentId, setInstrumentId] = useState("");
  const [instruments, setInstruments] = useState<{ id: string; symbol: string; exchange: string }[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [portfolios, setPortfolios] = useState<{ id: string; name: string }[]>([]);
  const [portfolio, setPortfolio] = useState("");
  const [page, setPage] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [revision, setRevision] = useState(0);
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [inbox, setInbox] = useState<{ enabled: boolean; items: unknown[] } | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([jsonRequest<{ items: typeof instruments }>("/market/instruments"),
      jsonRequest<{ items: typeof portfolios }>("/market/portfolios")]).then(([i, p]) => {
      if (active) { setInstruments(i.items); setPortfolios(p.items); }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    if (section === "imports") jsonRequest<{ enabled: boolean; items: unknown[] }>("/workspace/import-status")
      .then(d => { if (active) setInbox(d); }).catch(e => { if (active) setError(e.message); });
    if (section === "accounts" && admin) jsonRequest<{ items: User[] }>("/auth/users")
      .then(d => { if (active) setUsers(d.items); }).catch(e => { if (active) setError(e.message); });
    if (section === "proposals") jsonRequest<{ items: Proposal[]; next_offset: number | null }>(`/workspace/proposals?limit=20&offset=${page * 20}`)
      .then(d => { if (active) { setProposals(d.items); setHasNext(d.next_offset !== null); } }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [section, page, revision, admin]);
  async function act(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); setRevision(v => v + 1); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function template() {
    const source = { source_url: "https://example.org/remplacer-par-la-source", published_at: "2026-10-01T10:00:00Z", note: "À remplacer par la preuve du titre et des conventions.", confirmed: false };
    const examples = {
      data: { items: [{ kind: "earnings", instrument_id: instrumentId || "UUID_DU_TITRE", observation: {
        kind: "reported", fiscal_period_end: "2026-06-30", report_date: "2026-08-01", period_type: "quarterly",
        source_url: source.source_url, published_at: "2026-08-01T12:00:00Z", eps: "REMPLACER", currency: "USD", basis: "gaap_diluted",
      } }] },
      benchmark: { items: [{ ...source, series: "REFERENCE_USD", name: "Nom et version de l’indice", session_date: "2026-10-01", level: "REMPLACER", currency: "USD", convention: "net_total_return" }] },
      profile: { ...source, sector: "Secteur documenté", country: "FR", as_of: "2026-10-01" },
    };
    setText(JSON.stringify(examples[mode as keyof typeof examples], null, 2));
  }
  return <main className="mx-auto max-w-6xl px-5 py-8 text-slate-300">
    <PageHeader title="Mon espace" description="Importez des données sourcées, vérifiez les opérations proposées et gérez les accès de votre équipe." />
    <p className="mb-4 text-sm text-slate-400">{access.auth_enabled ? `Connecté : ${access.user?.username} · ${access.user?.role === "viewer" ? "Lecture seule" : access.user?.role === "admin" ? "Administration" : "Édition"}` : "Mode local sans authentification. Les recherches, alertes et simulations sont partagées."}</p>
    <SectionSwitch label="Paramètres de l’espace" value={section} onChange={s => { setSection(s); setError(""); setNotice(""); }} options={[
      { value: "imports", label: "Importer des données" }, { value: "proposals", label: "Opérations proposées" },
      ...(admin ? [{ value: "accounts", label: "Comptes de l’équipe" }] : []),
      ...(access.auth_enabled ? [{ value: "password", label: "Mon mot de passe" }] : []),
    ]} />
    {error && <p role="alert" className="mb-4 rounded-lg border border-amber-300/25 p-3 text-amber-300">{error}</p>}
    {notice && <p role="status" className="mb-4 text-signal">{notice}</p>}
    {section === "imports" && <section className="rounded-xl border border-white/10 p-4 sm:p-5">
      <h2 className="text-xl text-white">Compléter les données depuis un export</h2>
      <p className="my-3 text-sm leading-6 text-slate-400">Importez uniquement des données que vous êtes autorisé à utiliser, avec leur source et leurs conventions. Les champs absents ne sont pas devinés. Un import n’est pas une certification.</p>
      {!editor ? <p>Un compte en édition est nécessaire pour importer.</p> : <>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Type d’import<select className={input} value={mode} onChange={e => { setMode(e.target.value); setText(""); setResult(null); }}><option value="data">Résultats, valorisation, cours, taux et opérations</option><option value="benchmark">Historique d’un indice en USD</option><option value="profile">Secteur et pays documentés</option></select></label>
        <label className="text-sm">Titre pour la classification ou le modèle<select className={input} value={instrumentId} onChange={e => setInstrumentId(e.target.value)}><option value="">Choisir un titre</option>{instruments.map(i => <option key={i.id} value={i.id}>{i.symbol} · {i.exchange}</option>)}</select></label></div>
        <label className="mt-4 block text-sm">Fichier JSON autorisé (1 Mo maximum)<input className={input} type="file" accept=".json,application/json" onChange={async e => {
          const file = e.target.files?.[0]; if (!file) return;
          if (file.size > 1_000_000) { setError("Le fichier dépasse 1 Mo."); return; }
          setText(await file.text()); setResult(null);
        }} /></label>
        <details className="my-4"><summary className="cursor-pointer text-sm text-signal">Format de l’import et saisie avancée</summary>
          <p className="my-3 text-xs leading-5">Les identifiants doivent correspondre à des cotations suivies. Chaque ligne utilise son schéma documenté dans l’API. Les dividendes et splits sont conservés comme propositions, sans écriture automatique au portefeuille.</p>
          <button className="text-xs text-signal underline" onClick={template}>Afficher un modèle à compléter</button>
          <textarea aria-label="Contenu JSON de l’import" className={`${input} min-h-64 font-mono text-xs`} value={text} onChange={e => setText(e.target.value)} maxLength={1_000_000} />
        </details>
        <p className="mb-3 text-xs text-slate-400">{text ? `${text.length} caractères chargés. Vérifiez le contenu avant import.` : "Choisissez un fichier ou complétez le modèle."}</p>
        <button className={button} disabled={busy || !text || (mode === "profile" && !instrumentId)} onClick={() => act(async () => {
          let parsed; try { parsed = JSON.parse(text); } catch { throw new Error("Le fichier n’est pas un JSON valide."); }
          const path = mode === "benchmark" ? "/workspace/benchmarks/batch" : mode === "profile" ? `/workspace/instruments/${instrumentId}/profile` : "/workspace/imports";
          const response = await jsonRequest(path, parsed); setResult(response); setNotice("Traitement terminé. Consultez les acceptations et refus ci-dessous.");
        })}>Vérifier et importer</button>
        {result !== null && <pre className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-950 p-3 text-xs">{JSON.stringify(result, null, 2)}</pre>}
        <p className="mt-4 text-xs leading-5 text-slate-400">Un dossier local peut aussi alimenter ces imports automatiquement après configuration. Les sauvegardes et l’activation des comptes sont décrites dans la documentation du projet.</p>
        {inbox && <details className="mt-3 text-xs"><summary className="cursor-pointer text-signal">Imports automatiques : {inbox.enabled ? "activés" : "désactivés"} · {inbox.items.length} dernier(s) fichier(s)</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-950 p-3">{JSON.stringify(inbox.items, null, 2)}</pre></details>}
      </>}
    </section>}
    {section === "proposals" && <section>
      <h2 className="text-xl text-white">Dividendes et splits à examiner</h2>
      <p className="my-3 text-sm leading-6 text-slate-400">L’import ne change aucun solde. Après vérification, appliquez explicitement une proposition à une simulation. Les contrôles de détention, de devise et de doublon restent actifs.</p>
      <label className="block text-sm">Simulation concernée<select className={input} value={portfolio} onChange={e => { setPortfolio(e.target.value); setConfirmed({}); }}><option value="">Choisir une simulation</option>{portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <div id="proposal-results" className="mt-4 space-y-3">{proposals.map(p => <article key={p.id} className="rounded-xl border border-white/10 p-4">
        <h3 className="text-white">{instruments.find(i => i.id === p.instrument_id)?.symbol ?? "Titre non affiché"} · {p.kind === "split" ? `Split ${p.numerator}/${p.denominator}` : `Dividende net ${p.net_amount_per_security} ${p.currency}`}</h3>
        <p className="mt-2 text-sm">Date effective : {p.effective_date}{p.payment_date && ` · Paiement : ${p.payment_date}`}</p><p className="mt-2 text-xs leading-5">{p.note}</p>
        <a className="mt-2 inline-block text-xs text-signal underline" href={p.source_url} target="_blank" rel="noreferrer">Source publiée le {new Date(p.published_at).toLocaleDateString("fr-FR")}</a>
        {editor && <><label className="my-3 flex items-start gap-2 text-xs leading-5"><input type="checkbox" checked={confirmed[p.id] ?? false} onChange={e => setConfirmed(v => ({ ...v, [p.id]: e.target.checked }))} />J’ai vérifié la source, la cotation et les conventions pour cette simulation.</label><button className={button} disabled={busy || !portfolio || !confirmed[p.id]} onClick={() => act(async () => { await jsonRequest(`/workspace/proposals/${p.id}/apply`, { portfolio_id: portfolio, confirmed: true }); setConfirmed(v => ({ ...v, [p.id]: false })); setNotice("Opération traitée. Un doublon identique ne sera pas appliqué deux fois."); })}>Appliquer à la simulation</button></>}
      </article>)}</div>
      {!proposals.length && <p className="mt-4 text-sm text-slate-400">Aucune opération proposée.</p>}
      <Pagination page={page} pageSize={20} hasNext={hasNext} busy={busy} onChange={setPage} label="propositions" targetId="proposal-results" />
    </section>}
    {section === "accounts" && admin && <section className="rounded-xl border border-white/10 p-4 sm:p-5">
      <h2 className="text-xl text-white">Comptes de l’équipe</h2>
      <p className="my-3 text-sm leading-6 text-slate-400">Espace partagé : les comptes voient les mêmes recherches et simulations. Lecture seule consulte ; édition modifie ; administration gère aussi les comptes. Les changements de rôle ou désactivations révoquent les sessions concernées.</p>
      {!access.auth_enabled && <p className="mb-4 text-sm text-amber-300">Les comptes ne protègent pas encore le site. Créez un administrateur puis activez l’authentification selon la procédure de déploiement avant d’ouvrir l’accès.</p>}
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const d = new FormData(form); act(async () => {
        await jsonRequest("/auth/users", { username: d.get("username"), password: d.get("password"), role: d.get("role") }); form.reset(); setNotice("Compte créé. Transmettez ses accès par un canal approprié.");
      }); }}>
        <label className="text-sm">Identifiant<input className={input} name="username" required pattern="[a-z0-9_.-]{3,80}" maxLength={80} autoComplete="off" /></label>
        <label className="text-sm">Mot de passe initial<input className={input} name="password" type="password" required minLength={12} maxLength={256} autoComplete="new-password" /></label>
        <label className="text-sm">Rôle<select name="role" className={input} defaultValue="viewer"><option value="viewer">Lecture seule</option><option value="editor">Édition</option><option value="admin">Administration</option></select></label>
        <button className={`${button} self-end`} disabled={busy}>Créer le compte</button>
      </form>
      <ul className="mt-5 space-y-3">{users.map(u => <li key={u.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-3"><span>{u.username} · {u.enabled ? "Actif" : "Désactivé"}{access.user?.id === u.id && " · Vous"}</span><div className="flex flex-wrap gap-3"><select aria-label={`Rôle de ${u.username}`} className="rounded-lg border border-white/15 bg-slate-950 p-2 text-sm" value={u.role} disabled={busy} onChange={e => act(async () => { await jsonRequest(`/auth/users/${u.id}`, { role: e.target.value, enabled: u.enabled }, "PATCH"); if (u.id === access.user?.id) location.reload(); })}><option value="viewer">Lecture seule</option><option value="editor">Édition</option><option value="admin">Administration</option></select><button disabled={busy} className="text-sm text-signal underline" onClick={() => act(async () => { await jsonRequest(`/auth/users/${u.id}`, { role: u.role, enabled: !u.enabled }, "PATCH"); if (u.id === access.user?.id) location.reload(); })}>{u.enabled ? "Désactiver" : "Réactiver"}</button></div></li>)}</ul>
    </section>}
    {section === "password" && <section className="max-w-lg rounded-xl border border-white/10 p-5"><h2 className="text-xl text-white">Changer mon mot de passe</h2><form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); const d = new FormData(e.currentTarget); act(async () => {
      await jsonRequest("/auth/password", { current_password: d.get("current"), new_password: d.get("new") }); location.reload();
    }); }}><label className="block text-sm">Mot de passe actuel<input className={input} name="current" type="password" required autoComplete="current-password" maxLength={256} /></label><label className="block text-sm">Nouveau mot de passe<input className={input} name="new" type="password" required minLength={12} maxLength={256} autoComplete="new-password" /></label><p className="text-xs text-slate-400">Toutes vos sessions seront fermées après ce changement.</p><button disabled={busy} className={button}>Enregistrer et me reconnecter</button></form></section>}
  </main>;
}
