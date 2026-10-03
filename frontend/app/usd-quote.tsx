export type UsdQuote = {
  status: string; price_usd: string | null; stale: boolean;
  conversion: { currency: string; local_close: string; quote_multiplier: string;
    usd_per_unit: string; fx_date: string | null; fx_source_url: string | null } | null;
};

export function UsdQuoteDetails({ quote }: { quote: UsdQuote }) {
  if (quote.price_usd === null) return <span className="text-amber-300">{quote.status === "missing_fx" ? "Taux de conversion manquant" : quote.status === "invalid_conversion" ? "Conversion invalide" : "Cours manquant"}</span>;
  return <span>{new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 6 }).format(Number(quote.price_usd))} USD
    {quote.stale ? <span className="text-amber-300"> · données anciennes</span> : null}
    {quote.conversion?.fx_source_url ? <span className="block text-xs text-slate-400">1 {quote.conversion.currency} = {quote.conversion.usd_per_unit} USD · <a href={quote.conversion.fx_source_url} target="_blank" rel="noreferrer" className="underline">taux du {quote.conversion.fx_date}</a></span> : null}
  </span>;
}
