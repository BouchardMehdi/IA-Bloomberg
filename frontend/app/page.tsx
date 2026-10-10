"use client";

import { useEffect, useState } from "react";
import { EntityDetails, type EntityResolution } from "./entity-details";
import Link from "next/link";
import { PageHeader, Pagination } from "./components/ui";

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
  parent_event_id: string | null;
  entity_resolution: EntityResolution | null;
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
    id: string | null;
    status: string;
    coverage: {
      analyzed_count: number;
      selected_count: number;
      chunk_count: number;
      coverage_ratio: number;
      document_truncated: boolean;
      input_source: string;
      passages: Array<{ index: number; start: number; end: number; status: string }>;
    } | null;
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
  const [articleOffset, setArticleOffset] = useState(0);
  const [eventOffset, setEventOffset] = useState(0);
  const [articleError, setArticleError] = useState(false);
  const [eventError, setEventError] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

  useEffect(() => {
    const controller = new AbortController();
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

    fetch(`${apiUrl}/health/live`, { signal: controller.signal })
      .then((response) => setApiState(response.ok ? "online" : "offline"))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setApiState("offline");
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

    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiUrl}/articles?limit=6&offset=${articleOffset}`, { signal: controller.signal })
      .then(async r => { if (!r.ok) throw new Error(); return r.json() as Promise<ArticlePage>; })
      .then(d => { if (!controller.signal.aborted) { setArticles(d); setArticleError(false); } })
      .catch(() => { if (!controller.signal.aborted) setArticleError(true); });
    return () => controller.abort();
  }, [apiUrl, articleOffset]);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiUrl}/events?limit=6&offset=${eventOffset}`, { signal: controller.signal })
      .then(async r => { if (!r.ok) throw new Error(); return r.json() as Promise<EventPage>; })
      .then(d => { if (!controller.signal.aborted) { setEvents(d); setEventError(false); } })
      .catch(() => { if (!controller.signal.aborted) setEventError(true); });
    return () => controller.abort();
  }, [apiUrl, eventOffset]);

  const pillars = [
    {
      label: "Sources",
      value: "3",
      note: "BCE · Fed · SEC",
    },
    { label: "Documents", value: articles ? String(articles.total) : "—", note: "Collectés, sans doublons" },
    {
      label: "Événements",
      value: events ? String(events.total) : "—",
      note: "Détectés et traçables",
    },
  ];

  return (
    <main className="px-5 py-8 md:px-8">
      <div className="mx-auto max-w-6xl">
        <PageHeader title="Votre veille financière" description="Retrouvez les publications officielles et les faits extraits, puis ouvrez l’analyse d’un titre." eyebrow="Comprendre les marchés">
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
            {apiState === "checking" ? "Connexion en cours" : apiState === "online" ? "Service connecté" : "Service indisponible"}
          </div>
        </PageHeader>

        <section className="mb-6 grid gap-3 sm:grid-cols-3" aria-label="Accès rapides">
          {[["/analysis", "Analyser un titre", "Résultats, risques et valorisation"], ["/calendar", "Consulter les prochaines dates", "Calendrier et résultats sourcés"], ["/portfolio", "Suivre mon portefeuille", "Capital et performance simulée"]].map(([href, title, description]) => <Link key={href} href={href} className="rounded-xl border border-white/10 bg-white/[0.025] p-4 transition hover:border-signal/40"><span className="text-sm font-medium text-white">{title} <span className="text-signal" aria-hidden="true">↗</span></span><span className="mt-2 block text-xs text-slate-400">{description}</span></Link>)}
        </section>
        <section className="mb-6">
          <aside className="rounded-2xl border border-signal/20 bg-signal/5 p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-signal">État du système</p>
            <div className="mt-3 flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  latestRun?.status === "failed"
                    ? "bg-rose-400"
                    : latestRun?.status === "running"
                      ? "animate-pulse bg-amber-300"
                      : latestRun ? "bg-emerald-400" : "bg-slate-500"
                }`}
              />
              <p className="font-display text-2xl text-white">
                {latestRun?.status === "failed"
                  ? "Collecte en erreur"
                  : latestRun?.status === "running"
                    ? "Collecte en cours"
                    : latestRun?.status === "success" ? "Dernière collecte réussie" : "Aucune collecte observée"}
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
                Aucun historique de collecte disponible pour le moment.
              </p>
            )}
          </aside>
        </section>

        <section className="grid gap-3 sm:grid-cols-3 sm:gap-4">
          {pillars.map((item) => (
            <article key={item.label} className="overview-stat rounded-2xl border border-white/10 bg-white/[0.035] p-5">
              <div className="flex items-start justify-between">
                <p className="text-sm text-slate-400">{item.label}</p>
              </div>
              <p className="stat-value mt-4 font-display text-3xl text-white">{item.value}</p>
              <p className="stat-note mt-2 text-sm text-slate-500">{item.note}</p>
            </article>
          ))}
        </section>

        <section className="mt-8" id="events-list">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal">
                Événements sourcés
              </p>
              <h2 className="mt-2 font-display text-2xl text-white">Derniers événements</h2>
            </div>
            <span className="text-xs text-slate-500">{events?.total ?? "—"} événement(s)</span>
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
                  <p className="mt-2 text-xs text-slate-500">
                    {event.parent_event_id ? "Fait extrait d’une publication" : "Publication officielle"}
                  </p>
                  {event.semantic_analysis?.coverage ? (
                    <details className="mt-3 text-xs text-slate-400">
                      <summary className="cursor-pointer text-signal">
                        Couverture : {event.semantic_analysis.coverage.analyzed_count}/{event.semantic_analysis.coverage.selected_count} passages · {Math.round(event.semantic_analysis.coverage.coverage_ratio * 100)} % du texte
                      </summary>
                      <p className="mt-2">
                        {event.semantic_analysis.coverage.input_source === "rss" ? "Analyse de l’extrait RSS. " : "Analyse du texte récupéré. "}
                        {event.semantic_analysis.coverage.document_truncated ? "Document limité lors de la récupération. " : ""}
                        Les passages non retenus peuvent contenir d’autres faits.
                      </p>
                      <ul className="mt-2 space-y-1">
                        {event.semantic_analysis.coverage.passages.map((passage) => (
                          <li key={passage.index}>
                            Passage {passage.index + 1} · caractères {passage.start + 1}–{passage.end} : {passage.status === "success" ? "analysé" : passage.status === "failed" ? "échec" : passage.status === "not_selected" ? "non retenu" : "en attente"}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                  {event.companies.length ? (
                    <p className="mt-2 text-sm text-slate-300">
                      {event.parent_event_id ? "Sociétés du document : " : ""}
                      {event.companies.map((company) => company.name).join(", ")}
                      <span className="ml-2 text-xs text-slate-500">
                        CIK {event.companies[0].cik}
                      </span>
                    </p>
                  ) : null}
                  <EntityDetails resolution={event.entity_resolution} />
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
                        Document utilisé pour l’analyse
                      </a>
                    ) : null}
                  </details>
                </article>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-white/15 px-6 py-10 text-center text-sm text-slate-400">
              {eventError ? "Les événements n’ont pas pu être chargés. Réessaie en rechargeant la page." : !events ? "Chargement des événements…" : "Aucun événement extrait pour le moment."}
            </div>
          )}
          {events && <Pagination page={eventOffset / 6} pageSize={6} total={events.total} label="événements" onChange={p => { setEvents(null); setEventOffset(p * 6); document.getElementById("events-list")?.scrollIntoView({ behavior: "smooth" }); }} />}
        </section>

        <section className="mt-8" id="articles-list">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal">
                Sources primaires
              </p>
              <h2 className="mt-2 font-display text-2xl text-white">Dernières publications</h2>
            </div>
            <span className="text-xs text-slate-500">{articles?.total ?? "—"} article(s)</span>
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
                      {article.published_at ? "Publié le " : "Consulté le "}
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
              <p className="text-sm text-slate-400">{articleError ? "Les publications n’ont pas pu être chargées. Réessaie en rechargeant la page." : !articles ? "Chargement des publications…" : "Aucune publication collectée pour le moment."}</p>
            </div>
          )}
          {articles && <Pagination page={articleOffset / 6} pageSize={6} total={articles.total} label="publications" onChange={p => { setArticles(null); setArticleOffset(p * 6); document.getElementById("articles-list")?.scrollIntoView({ behavior: "smooth" }); }} />}
        </section>

        <footer className="mt-20 flex flex-col gap-2 border-t border-white/10 py-6 text-xs text-slate-500 sm:flex-row sm:justify-between">
          <span>Une publication est un document. Un événement est un fait extrait à vérifier.</span>
          <Link href="/coverage" className="text-signal">Vérifier la qualité des données →</Link>
        </footer>
      </div>
    </main>
  );
}
