"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { jsonRequest } from "../lib/api";
import { useAccess } from "./access-provider";

const pages = [
  { href: "/", label: "Veille", detail: "Actualités et faits sourcés", icon: "M4 5h16v14H4z M8 9h8 M8 13h5" },
  { href: "/analysis", label: "Analyser", detail: "Comprendre un titre", icon: "M4 19h16 M7 15V9 M12 15V5 M17 15v-4" },
  { href: "/calendar", label: "Calendrier", detail: "Dates et résultats", icon: "M4 6h16v14H4z M8 3v6 M16 3v6 M4 11h16" },
  { href: "/portfolio", label: "Portefeuille", detail: "Suivre une simulation", icon: "M3 8h18v12H3z M8 8V4h8v4 M3 13h18 M10 13v3h4v-3" },
  { href: "/coverage", label: "Qualité des données", detail: "Repérer ce qui manque", icon: "M12 3l8 4v5c0 5-8 9-8 9s-8-4-8-9V7z M8 12l3 3 5-6" },
  { href: "/international", label: "International", detail: "Cotations et devises", icon: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c5 5 5 13 0 18 M12 3c-5 5-5 13 0 18" },
  { href: "/alerts", label: "Alertes", detail: "Nouveautés et suivi", icon: "M6 9a6 6 0 0 1 12 0v6l2 3H4l2-3z M10 21h4" },
  { href: "/settings", label: "Mon espace", detail: "Imports et accès", icon: "M4 4h16v16H4z M8 9h8 M8 15h8 M10 7v4 M14 13v4" },
  { href: "/briefing", label: "Briefing quotidien", detail: "Votre liste de lecture", icon: "M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h5" },
  { href: "/journal", label: "Journal des décisions", detail: "Hypothèses et suivi", icon: "M4 4h16v16H4z M8 8h8 M8 12h8 M8 16h4" },
  { href: "/collections", label: "Suivi des collectes", detail: "État et reprises", icon: "M4 18V6 M4 18h16 M8 14v-4 M12 14V5 M16 14V8 M20 14v-3" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const access = useAccess();
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let active = true;
    const refresh = () => { jsonRequest<{ unread_count: number }>("/workspace/alerts?limit=1")
      .then(d => { if (active) setUnread(d.unread_count); }).catch(() => {}); };
    refresh();
    const timer = window.setInterval(refresh, 60000);
    window.addEventListener("market-ai:alerts-changed", refresh);
    return () => { active = false; clearInterval(timer); window.removeEventListener("market-ai:alerts-changed", refresh); };
  }, []);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const menuOpen = menuFor === pathname;
  const toggle = useRef<HTMLButtonElement>(null);
  const current = pages.find(p => p.href === pathname);
  function links(mobile = false) {
    return pages.map(p => <Link key={p.href} href={p.href} aria-current={pathname === p.href ? "page" : undefined}
      onClick={() => setMenuFor(null)} className={`app-nav-link ${pathname === p.href ? "is-active" : ""}`}>
      <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={p.icon} /></svg>
      <span><span className="block font-medium">{p.label}{p.href === "/alerts" && unread > 0 && <span className="ml-2 rounded-full bg-signal/15 px-2 py-0.5 text-xs text-signal" aria-label={`${unread} non lues`}>{unread > 99 ? "99+" : unread}</span>}</span>{!mobile && <span className="mt-1 block text-xs text-slate-400">{p.detail}</span>}</span>
      {pathname === p.href && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-signal" aria-hidden="true" />}
    </Link>);
  }
  return <div className="app-shell">
    <a className="skip-link" href="#page-content">Aller au contenu</a>
    <aside className="app-sidebar">
      <Link href="/" className="app-brand" aria-label="Market AI — accueil"><span className="brand-mark" aria-hidden="true">M<span>↗</span></span><span>Market <span className="text-signal">AI</span><small>Recherche financière</small></span></Link>
      <p className="mb-3 mt-10 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Votre espace</p>
      <nav aria-label="Navigation principale" className="space-y-1">{links()}</nav>
      <div className="mt-auto rounded-xl border border-white/10 bg-white/[0.025] p-4">
        <span className="text-xs font-medium text-signal">Des décisions documentées</span>
        <p className="mt-2 text-xs leading-5 text-slate-400">Chaque analyse garde ses sources. Les opérations du portefeuille sont simulées.</p>
      </div>
    </aside>
    <div className="app-workspace">
      <header className="app-topbar">
        <Link href="/" className="flex items-center gap-2 font-semibold text-white lg:hidden"><span className="brand-mark small" aria-hidden="true">M</span>Market AI</Link>
        <div className="hidden items-center gap-3 text-sm lg:flex"><span className="text-slate-500">Espace de recherche</span><span aria-hidden="true" className="text-slate-600">/</span><span className="text-slate-200">{current?.label ?? "Market AI"}</span></div>
        <span className="ml-auto hidden rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-400 sm:block">Portefeuille simulé</span>
        {access.auth_enabled && <button className="ml-3 text-xs text-signal underline" onClick={async () => { try { await jsonRequest("/auth/logout", {}); location.reload(); } catch { window.dispatchEvent(new Event("market-ai:session-expired")); } }}>Déconnexion</button>}
        <button ref={toggle} type="button" aria-expanded={menuOpen} aria-controls="mobile-navigation" aria-label={menuOpen ? "Fermer la navigation" : "Ouvrir la navigation"}
          onClick={() => setMenuFor(menuOpen ? null : pathname)} className="ml-auto flex items-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-sm text-white sm:ml-2 lg:hidden">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d={menuOpen ? "M6 6l12 12 M6 18L18 6" : "M4 6h16 M4 12h16 M4 18h16"} /></svg>Menu
        </button>
      </header>
      <nav id="mobile-navigation" aria-label="Navigation mobile" hidden={!menuOpen} className="mobile-navigation lg:!hidden"
        onKeyDown={e => { if (e.key === "Escape") { setMenuFor(null); toggle.current?.focus(); } }}>{links(true)}</nav>
      {access.user?.role === "viewer" && <p className="border-b border-white/10 px-5 py-2 text-xs text-amber-300">Accès en lecture seule. Les modifications sont réservées aux comptes en édition.</p>}
      <div id="page-content" tabIndex={-1} className="min-w-0 outline-none">{children}</div>
      <footer className="app-footer"><span>Market AI · Sources vérifiables, limites visibles</span><span>Recherche et simulation</span></footer>
    </div>
  </div>;
}
