"use client";

import { useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Snapshot = { value: string | null; start: string; end: string;
  sources: { id: string; url: string; filed: string; accession: string; value: string }[] };
type Trend = { metric: string; concept: string; unit: string; status: string;
  current: Snapshot; previous: Snapshot | null; delta: string | null;
  percent: string | null; reason: string; direction: string | null };
type Data = { items: Trend[]; notice: string; reason: string | null;
  coverage: { limited: boolean; examined: number; limit: number } };
function Period({ data, unit, label }: { data: Snapshot; unit: string; label: string }) {
  return <div className="my-2 text-sm"><p className="text-white">{label} : {data.value ?? "valeurs contradictoires"} {unit}</p><p>Du {data.start} au {data.end}</p><ul className="mt-2 text-xs">{data.sources.map((s) => <li key={s.id}><a className="text-signal underline" href={s.url} target="_blank" rel="noreferrer">Dépôt SEC</a> · {s.filed} · {s.accession}{data.value === null ? ` · valeur : ${s.value}` : ""}</li>)}</ul></div>;
}
export function FinancialTrends({ instrumentId }: { instrumentId: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${api}/market/instruments/${instrumentId}/financial-trends`, { cache: "no-store", signal: controller.signal })
      .then(async (r) => { if (!r.ok) throw new Error("Comparaisons indisponibles."); return r.json() as Promise<Data>; })
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [instrumentId, revision]);
  return <section className="my-5 rounded-xl border border-white/10 p-5">
    <div className="flex flex-wrap justify-between gap-3"><h2 className="text-xl text-white">Évolution du chiffre d’affaires et des bénéfices</h2><button className="text-sm text-signal underline" onClick={() => { setData(null); setError(""); setRevision((n) => n + 1); }}>Actualiser les comparaisons</button></div>
    {error ? <p role="alert" className="mt-3 text-rose-300">{error}</p> : null}
    {!data && !error ? <p role="status" className="mt-3">Chargement…</p> : null}
    {data ? <><p className="my-3 text-sm">{data.notice}</p><p className="my-2 text-xs">Comparaison avec la période de l’année précédente publiée dans le même dépôt, à durée strictement identique. Les années de 53 semaines et durées différentes restent bloquées. {data.coverage.examined}/{data.coverage.limit} observations examinées.</p>
      {data.reason ? <p className="my-3 text-amber-300">{data.reason}</p> : null}
      {!data.items.length ? <p className="my-3 text-sm">Aucune comparaison disponible dans cette couverture.</p> : null}
      {data.items.map((item) => <article key={`${item.metric}-${item.concept}-${item.unit}-${item.current.start}-${item.current.end}`} className="my-4 rounded border border-white/10 p-4"><h3 className="text-lg text-white">{item.metric === "revenue" ? "Chiffre d’affaires" : "Résultat net"}</h3><p className="mt-1 break-words text-xs">{item.concept} · {item.unit}</p><div className="grid gap-3 md:grid-cols-2"><Period data={item.current} unit={item.unit} label="Période actuelle" />{item.previous ? <Period data={item.previous} unit={item.unit} label="Période précédente comparable" /> : null}</div>
        {item.status === "comparable" ? <p className="my-3 text-white">Variation : {item.delta} {item.unit}{item.percent !== null ? ` · ${item.percent} %` : " · pourcentage non calculé"}{item.direction === "turned_profitable" ? " · passage de perte à bénéfice" : item.direction === "turned_loss" ? " · passage de bénéfice à perte" : ""}</p> : <p className="my-3 text-amber-300">Comparaison bloquée</p>}
        <p className="text-xs">{item.reason}</p>
      </article>)}
    </> : null}
  </section>;
}
