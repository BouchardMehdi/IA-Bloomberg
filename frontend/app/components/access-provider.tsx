"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { jsonRequest } from "../lib/api";

export type User = { id: string; username: string; role: "admin" | "editor" | "viewer"; enabled: boolean };
type Access = { auth_enabled: boolean; user: User | null };
const AccessContext = createContext<Access>({ auth_enabled: false, user: null });
export const useAccess = () => useContext(AccessContext);

export function AccessProvider({ children }: { children: React.ReactNode }) {
  const [access, setAccess] = useState<Access | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    jsonRequest<Access>("/auth/me").then(a => { if (active) setAccess(a); })
      .catch(() => { if (active) setError("Impossible de vérifier l’accès. Vérifiez que le serveur est démarré."); });
    function expired() { setAccess({ auth_enabled: true, user: null }); }
    window.addEventListener("market-ai:session-expired", expired);
    return () => { active = false; window.removeEventListener("market-ai:session-expired", expired); };
  }, []);
  if (access && (!access.auth_enabled || access.user)) return <AccessContext.Provider value={access}>{children}</AccessContext.Provider>;
  return <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-5 px-5 py-10 text-slate-300">
    <h1 className="font-display text-3xl text-white">Market <span className="text-signal">AI</span></h1>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
    {!access ? <><p>Vérification de l’accès…</p>{error && <button className="rounded-lg border border-white/20 p-3" onClick={() => location.reload()}>Réessayer</button>}</> : <>
      <p>Connectez-vous à l’espace de recherche partagé.</p>
      <form className="space-y-4" onSubmit={async e => {
        e.preventDefault(); setBusy(true); setError("");
        const data = new FormData(e.currentTarget);
        try {
          const user = await jsonRequest<User>("/auth/login", { username: data.get("username"), password: data.get("password") });
          setAccess({ auth_enabled: true, user });
        } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
      }}>
        <label className="block text-sm">Identifiant<input className="mt-1 w-full rounded-lg border border-white/20 bg-slate-950 p-3" name="username" autoComplete="username" required maxLength={80} /></label>
        <label className="block text-sm">Mot de passe<input className="mt-1 w-full rounded-lg border border-white/20 bg-slate-950 p-3" name="password" type="password" autoComplete="current-password" required maxLength={256} /></label>
        <button disabled={busy} className="w-full rounded-lg bg-signal p-3 font-semibold text-slate-950 disabled:opacity-40">{busy ? "Connexion…" : "Se connecter"}</button>
      </form>
      <p className="text-xs text-slate-400">Un administrateur doit vous fournir un compte. Les portefeuilles et les recherches sont partagés avec l’équipe.</p>
    </>}
  </main>;
}
