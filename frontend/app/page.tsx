"use client";

import { useEffect, useState } from "react";

type ApiState = "checking" | "online" | "offline";

const pillars = [
  { label: "Sources", value: "0", note: "Collecteurs à venir" },
  { label: "Événements", value: "0", note: "Base prête" },
  { label: "Rapports", value: "0", note: "Moteur à venir" },
];

export default function Home() {
  const [apiState, setApiState] = useState<ApiState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

    fetch(`${apiUrl}/health/live`, { signal: controller.signal })
      .then((response) => setApiState(response.ok ? "online" : "offline"))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setApiState("offline");
      });

    return () => controller.abort();
  }, []);

  return (
    <main className="min-h-screen px-5 py-6 md:px-10 md:py-10">
      <div className="mx-auto max-w-6xl">
        <header className="flex items-center justify-between border-b border-white/10 pb-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-signal">Market AI</p>
            <h1 className="mt-1 font-display text-xl font-medium text-white">Centre de veille</h1>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-300">
            <span
              className={`h-2 w-2 rounded-full ${
                apiState === "online"
                  ? "bg-emerald-400"
                  : apiState === "offline"
                    ? "bg-rose-400"
                    : "animate-pulse bg-amber-300"
              }`}
            />
            API {apiState === "checking" ? "vérification" : apiState === "online" ? "active" : "indisponible"}
          </div>
        </header>

        <section className="grid gap-8 py-16 lg:grid-cols-[1.4fr_0.6fr] lg:items-end">
          <div>
            <p className="mb-4 text-sm text-slate-400">Fondation · Version 0.1</p>
            <h2 className="max-w-3xl font-display text-4xl font-medium leading-tight text-white md:text-6xl">
              Comprendre ce qui compte sur les marchés.
            </h2>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-400 md:text-lg">
              Une veille financière qui transforme des sources vérifiables en événements structurés,
              sans perdre leur provenance.
            </p>
          </div>
          <aside className="rounded-2xl border border-signal/20 bg-signal/5 p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-signal">État du système</p>
            <p className="mt-3 font-display text-2xl text-white">Socle opérationnel</p>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              API, stockage, cache et interface sont prêts à accueillir le premier pipeline de collecte.
            </p>
          </aside>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          {pillars.map((item) => (
            <article key={item.label} className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
              <div className="flex items-start justify-between">
                <p className="text-sm text-slate-400">{item.label}</p>
                <span className="rounded-full bg-white/5 px-2 py-1 text-[10px] uppercase tracking-wider text-slate-500">
                  initial
                </span>
              </div>
              <p className="mt-8 font-display text-4xl text-white">{item.value}</p>
              <p className="mt-2 text-sm text-slate-500">{item.note}</p>
            </article>
          ))}
        </section>

        <footer className="mt-20 flex flex-col gap-2 border-t border-white/10 py-6 text-xs text-slate-500 sm:flex-row sm:justify-between">
          <span>Article ≠ Event</span>
          <span>Sources traçables · Mémoire PostgreSQL</span>
        </footer>
      </div>
    </main>
  );
}
