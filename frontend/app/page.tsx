"use client";

import { useEffect, useState } from "react";

type ApiState = "checking" | "online" | "offline";

type Article = {
  id: string;
  source_name: string;
  url: string;
  title: string;
  content: string | null;
  language: string | null;
  published_at: string | null;
  fetched_at: string;
  content_status: string;
  content_truncated: boolean;
};

type ArticlePage = {
  items: Article[];
  total: number;
  limit: number;
  offset: number;
};

type CollectionRun = {
  id: string;
  source_name: string;
  trigger: "manual" | "scheduled";
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  fetched_count: number;
  inserted_count: number;
  duplicate_count: number;
  error_message: string | null;
};

type CollectionRunPage = {
  items: CollectionRun[];
  total: number;
};

type MarketEvent = {
  id: string;
  event_type: string;
  title: string;
  description: string | null;
  event_datetime: string | null;
  status: string;
  extraction_method: string | null;
  extraction_version: string | null;
  evidence_excerpt: string | null;
  structured_data: Record<string, unknown> | null;
  confidence_score: number | null;
  country: string | null;
  region: string | null;
  source_name: string;
  article_url: string;
  sources: Array<{
    article_id: string;
    source_name: string;
    url: string;
    document_url: string | null;
    published_at: string | null;
    content_status: string;
  }>;
  companies: Array<{
    id: string;
    cik: string;
    name: string;
    role: string;
  }>;
  semantic_analysis: {
    model_name: string;
    prompt_version: string;
    duration_ms: number | null;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    source_url: string | null;
    result: {
      summary?: string;
      importance_score?: number;
      urgency_score?: number;
      evidence?: Array<{ claim: string; quote: string }>;
    };
  } | null;
};

type EventPage = {
  items: MarketEvent[];
  total: number;
};

export default function Home() {
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [articles, setArticles] = useState<ArticlePage | null>(null);
  const [events, setEvents] = useState<EventPage | null>(null);
  const [latestRun, setLatestRun] = useState<CollectionRun | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

    fetch(`${apiUrl}/health/live`, { signal: controller.signal })
      .then((response) => setApiState(response.ok ? "online" : "offline"))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setApiState("offline");
      });

    fetch(`${apiUrl}/articles?limit=6`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Articles unavailable");
        return response.json() as Promise<ArticlePage>;
      })
      .then(setArticles)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setArticles(null);
      });

    fetch(`${apiUrl}/collection-runs?limit=1`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Collection history unavailable");
        return response.json() as Promise<CollectionRunPage>;
      })
      .then((page) => setLatestRun(page.items[0] ?? null))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setLatestRun(null);
      });

    fetch(`${apiUrl}/events?limit=5`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Events unavailable");
        return response.json() as Promise<EventPage>;
      })
      .then(setEvents)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setEvents(null);
      });

    return () => controller.abort();
  }, []);

  const pillars = [
    {
      label: "Sources",
      value: "3",
      note: "BCE · Fed · SEC",
    },
    { label: "Articles", value: String(articles?.total ?? 0), note: "Entrées dédupliquées" },
    {
      label: "Événements",
      value: String(events?.total ?? 0),
      note: "Détectés et traçables",
    },
  ];

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
            <div className="mt-3 flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  latestRun?.status === "failed"
                    ? "bg-rose-400"
                    : latestRun?.status === "running"
                      ? "animate-pulse bg-amber-300"
                      : "bg-emerald-400"
                }`}
              />
              <p className="font-display text-2xl text-white">
                {latestRun?.status === "failed"
                  ? "Collecte en erreur"
                  : latestRun?.status === "running"
                    ? "Collecte en cours"
                    : "Pipeline opérationnel"}
              </p>
            </div>
            {latestRun ? (
              <div className="mt-4 grid grid-cols-3 gap-3 border-t border-white/10 pt-4 text-center">
                <div>
                  <p className="font-display text-xl text-white">{latestRun.fetched_count}</p>
                  <p className="text-[10px] uppercase tracking-wide text-slate-500">Lus</p>
                </div>
                <div>
                  <p className="font-display text-xl text-white">{latestRun.inserted_count}</p>
                  <p className="text-[10px] uppercase tracking-wide text-slate-500">Nouveaux</p>
                </div>
                <div>
                  <p className="font-display text-xl text-white">{latestRun.duration_ms ?? "—"}</p>
                  <p className="text-[10px] uppercase tracking-wide text-slate-500">ms</p>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Le scheduler attend sa première exécution enregistrée.
              </p>
            )}
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

        <section className="mt-16">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal">
                Événements sourcés
              </p>
              <h3 className="mt-2 font-display text-2xl text-white">Derniers événements</h3>
            </div>
            <span className="text-xs text-slate-500">{events?.total ?? 0} événement(s)</span>
          </div>

          {events?.items.length ? (
            <div className="grid gap-4 md:grid-cols-2">
              {events.items.map((event) => (
                <article
                  key={event.id}
                  className="rounded-2xl border border-white/10 bg-white/[0.025] p-5 transition hover:border-signal/30 hover:bg-white/[0.04]"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs font-medium text-signal">{event.source_name}</span>
                    <span className="rounded-full bg-white/5 px-2 py-1 text-[10px] uppercase tracking-wider text-slate-500">
                      {event.event_type.replaceAll("_", " ")}
                    </span>
                  </div>
                  <h4 className="mt-4 font-display text-lg text-white">
                    <a href={event.article_url} target="_blank" rel="noreferrer">{event.title}</a>
                  </h4>
                  {event.companies.length ? (
                    <p className="mt-2 text-sm text-slate-300">
                      {event.companies.map((company) => company.name).join(", ")}
                      <span className="ml-2 text-xs text-slate-500">
                        CIK {event.companies[0].cik}
                      </span>
                    </p>
                  ) : null}
                  {event.semantic_analysis?.result.summary ? (
                    <p className="mt-3 text-sm leading-6 text-slate-300">
                      {event.semantic_analysis.result.summary}
                    </p>
                  ) : null}
                  {event.evidence_excerpt ? (
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-400">
                      {event.evidence_excerpt}
                    </p>
                  ) : null}
                  <time className="mt-3 block text-xs text-slate-500">
                    {event.event_datetime
                      ? new Intl.DateTimeFormat("fr-FR", {
                          dateStyle: "medium",
                          timeStyle: "short",
                        }).format(new Date(event.event_datetime))
                      : "Date inconnue"}
                  </time>
                  <details className="mt-3 text-xs text-slate-400">
                    <summary className="cursor-pointer text-signal">Sources et preuves ({event.sources.length})</summary>
                    <ul className="mt-2 space-y-2">
                      {event.sources.map((source) => (
                        <li key={source.article_id}>
                          <a href={source.document_url ?? source.url} target="_blank" rel="noreferrer" className="underline">
                            {source.source_name}
                          </a>
                          {source.published_at ? ` · ${new Date(source.published_at).toLocaleDateString("fr-FR")}` : " · Date inconnue"}
                          {source.content_status === "success" ? " · Texte récupéré" : " · Extrait RSS"}
                        </li>
                      ))}
                    </ul>
                    {event.semantic_analysis?.result.evidence?.map((item, index) => (
                      <blockquote key={index} className="mt-2 border-l border-signal/40 pl-3">
                        {item.quote}
                      </blockquote>
                    ))}
                    {event.semantic_analysis?.source_url ? (
                      <a href={event.semantic_analysis.source_url} target="_blank" rel="noreferrer" className="mt-2 block underline">
                        Document utilisé pour l’analyse (passage limité)
                      </a>
                    ) : null}
                  </details>
                </article>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-white/15 px-6 py-10 text-center text-sm text-slate-400">
              Aucun événement extrait pour le moment.
            </div>
          )}
        </section>

        <section className="mt-16">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal">
                Sources primaires
              </p>
              <h3 className="mt-2 font-display text-2xl text-white">Dernières publications</h3>
            </div>
            <span className="text-xs text-slate-500">{articles?.total ?? 0} article(s)</span>
          </div>

          {articles?.items.length ? (
            <div className="divide-y divide-white/10 rounded-2xl border border-white/10 bg-white/[0.025]">
              {articles.items.map((article) => (
                <a
                  key={article.id}
                  href={article.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group grid gap-3 p-5 transition hover:bg-white/[0.04] md:grid-cols-[150px_1fr_24px] md:items-start"
                >
                  <div>
                    <p className="text-xs font-medium text-signal">{article.source_name}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      {article.content_status === "success"
                        ? (article.content_truncated ? "Texte récupéré (limité)" : "Texte récupéré")
                        : article.content_status === "pending" || article.content_status === "fetching"
                          ? "Récupération du texte en cours"
                          : "Extrait RSS disponible"}
                    </p>
                    <time className="mt-1 block text-xs text-slate-500">
                      {new Intl.DateTimeFormat("fr-FR", {
                        dateStyle: "medium",
                        timeStyle: "short",
                      }).format(new Date(article.published_at ?? article.fetched_at))}
                    </time>
                  </div>
                  <div>
                    <h4 className="font-display text-lg text-white group-hover:text-signal">
                      {article.title}
                    </h4>
                    {article.content ? (
                      <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-400">
                        {article.content}
                      </p>
                    ) : null}
                  </div>
                  <span aria-hidden className="text-slate-500 transition group-hover:translate-x-1 group-hover:text-signal">
                    ↗
                  </span>
                </a>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-white/15 px-6 py-10 text-center">
              <p className="text-sm text-slate-400">Aucun article collecté pour le moment.</p>
              <code className="mt-3 inline-block rounded bg-black/20 px-3 py-2 text-xs text-slate-500">
                docker compose exec backend python -m app.cli.collect_ecb
              </code>
            </div>
          )}
        </section>

        <footer className="mt-20 flex flex-col gap-2 border-t border-white/10 py-6 text-xs text-slate-500 sm:flex-row sm:justify-between">
          <span>Article ≠ Event</span>
          <span>Sources traçables · Mémoire PostgreSQL</span>
        </footer>
      </div>
    </main>
  );
}
