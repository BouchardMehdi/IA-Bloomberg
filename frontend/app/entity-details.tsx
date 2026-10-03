export type EntityResolution = {
  version: string;
  resolved_at: string;
  registry: { url: string; observed_at: string; published_at: string | null } | null;
  entities: Array<{
    name: string;
    kind: string;
    role: string;
    quote: string | null;
    status: string;
    method: string | null;
    candidates: Array<{
      cik?: string;
      name?: string;
      ticker?: string;
      exchange?: string | null;
      code?: string;
      listings?: Array<{ ticker: string; exchange: string | null }>;
    }>;
  }>;
};

const statuses: Record<string, string> = {
  resolved: "Identifié", ambiguous: "Ambigu", unresolved: "Non identifié", unverified: "Mention non vérifiée",
};
const roles: Record<string, string> = {
  subject: "Sujet", counterparty: "Contrepartie", mention: "Mention", source_subject: "Déclarant du document",
};

export function EntityDetails({ resolution }: { resolution: EntityResolution | null }) {
  if (!resolution?.entities.length) return null;
  return (
    <details className="mt-3 text-xs text-slate-400">
      <summary className="cursor-pointer text-signal">Sociétés et titres ({resolution.entities.length})</summary>
      <ul className="mt-2 space-y-3">
        {resolution.entities.map((entity, index) => (
          <li key={`${entity.name}-${index}`}>
            <p className="text-slate-300">{entity.name} · {roles[entity.role] ?? entity.role} · {statuses[entity.status] ?? entity.status}</p>
            {entity.candidates.map((candidate, i) => (
              <p key={i} className="mt-1">
                {candidate.name ?? candidate.code ?? candidate.ticker}
                {candidate.cik ? ` · CIK ${candidate.cik}` : ""}
                {candidate.ticker ? ` · ${candidate.ticker} (${candidate.exchange ?? "marché inconnu"})` : ""}
                {candidate.listings?.length ? ` · Cotations : ${candidate.listings.map((listing) => `${listing.ticker} (${listing.exchange ?? "marché inconnu"})`).join(", ")}` : ""}
              </p>
            ))}
            {entity.quote ? <blockquote className="mt-1 border-l border-signal/40 pl-3">{entity.quote}</blockquote> : null}
          </li>
        ))}
      </ul>
      {resolution.registry ? (
        <p className="mt-3">
          <a href={resolution.registry.url} target="_blank" rel="noreferrer" className="underline">Référentiel SEC</a>
          {` · Consulté le ${new Date(resolution.registry.observed_at).toLocaleDateString("fr-FR")}`}
          <span className="block mt-1">Les cotations sont celles du référentiel consulté. La classe du titre et sa cotation à la date du fait ne sont pas garanties.</span>
        </p>
      ) : null}
    </details>
  );
}
