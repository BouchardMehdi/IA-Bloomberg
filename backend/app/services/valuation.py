import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.models.market import MarketInstrument
from app.models.valuation import ValuationObservation
from app.schemas.valuation import ValuationInput
from app.services.market_data import MarketDataService


def security_identity(instrument):
    return {
        "symbol": instrument.symbol,
        "exchange": instrument.exchange,
        "cik": instrument.cik,
        "isin": instrument.isin,
    }


def ratio_text(value):
    rounded = value.quantize(Decimal("0.01"))
    return str(value) if value != 0 and rounded == 0 else str(rounded)


def calculate_valuation(instrument, price, observation: dict | None, now: datetime):
    result = {
        "status": "blocked",
        "reasons": [],
        "pe": None,
        "earnings_yield_percent": None,
        "reference_comparison": None,
        "normalized_price": None,
    }
    reasons = result["reasons"]
    if price is None:
        reasons.append("Cours local manquant.")
    elif (
        price.session_date > now.date()
        or (now.date() - price.session_date).days > get_settings().market_max_price_age_days
    ):
        reasons.append("Clôture locale future ou trop ancienne.")
    if observation is None:
        reasons.append("BPA annuel dilué par titre et preuve de correspondance manquants.")
        return result
    try:
        data = ValuationInput.model_validate(
            {k: v for k, v in observation.items() if k != "security_identity"}
        )
    except ValueError:
        reasons.append("Observation de valorisation incompatible ou incomplète.")
        return result
    if observation.get("security_identity") != security_identity(instrument):
        reasons.append("Identité du titre modifiée ou non conservée avec la preuve.")
    if data.currency != instrument.currency or data.quote_multiplier != instrument.quote_multiplier:
        reasons.append("Devise ou unité de cotation différente de l’observation fournie.")
    if price and data.valuation_date != price.session_date:
        reasons.append("L’observation ne couvre pas la dernière séance : preuve à actualiser.")
    if price and price.quote_context:
        quote = price.quote_context
        if quote.get("adjusted") is True or any(
            key in quote and str(quote[key]) != str(value)
            for key, value in {
                "symbol": instrument.symbol,
                "exchange": instrument.exchange,
                "currency": instrument.currency,
            }.items()
        ):
            reasons.append("Contexte du cours incompatible avec la cotation et son cours brut.")
        if "quote_multiplier" in quote:
            try:
                multiplier = Decimal(str(quote["quote_multiplier"]))
                valid = multiplier.is_finite() and multiplier == instrument.quote_multiplier
            except (ValueError, InvalidOperation):
                valid = False
            if not valid:
                reasons.append("Unité historique du cours incompatible.")
    if (data.valuation_date - data.period_end).days > 550:
        reasons.append("Résultats annuels trop anciens : plus de 550 jours avant la séance.")
    if data.eps_per_security <= 0:
        reasons.append("Bénéfice nul ou perte : PER non significatif, calcul bloqué.")
    if price and (not price.close.is_finite() or price.close <= 0):
        reasons.append("Cours non positif ou invalide.")
    if reasons:
        return result
    with localcontext() as context:
        context.prec = 50
        normalized = price.close * data.quote_multiplier
        pe = normalized / data.eps_per_security
        result.update(
            status="available",
            normalized_price=str(normalized),
            pe=ratio_text(pe),
            earnings_yield_percent=ratio_text(100 / pe),
        )
        if data.reference:
            reference = data.reference.value
            result["reference_comparison"] = {
                "position": "higher" if pe > reference else "lower" if pe < reference else "equal",
                "difference_percent": ratio_text((pe / reference - 1) * 100),
                "reference": data.reference.model_dump(mode="json"),
                "notice": "Multiple supérieur/inférieur à cette référence fournie ; "
                "ni surévaluation/sous-évaluation avérée, ni signal d’achat.",
            }
    return result


class ValuationService:
    def __init__(self, session):
        self.session = session

    async def add_batch(self, request):
        results = []
        for item in request.items:
            try:
                result = await self.add(item.instrument_id, item.observation)
                results.append({"instrument_id": item.instrument_id, "status": "saved", **result})
            except (LookupError, ValueError) as exc:
                await self.session.rollback()
                results.append(
                    {"instrument_id": item.instrument_id, "status": "rejected", "reason": str(exc)}
                )
        return {"items": results, "saved_count": sum(r["status"] == "saved" for r in results)}

    async def add(self, instrument_id: UUID, request: ValuationInput):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            raise LookupError("Titre introuvable.")
        if (
            request.currency != instrument.currency
            or request.quote_multiplier != instrument.quote_multiplier
        ):
            raise ValueError("Devise et multiplicateur doivent correspondre au titre suivi.")
        data = request.model_dump(mode="json")
        data["security_identity"] = security_identity(instrument)
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        identifier = (
            await self.session.execute(
                insert(ValuationObservation)
                .values(
                    instrument_id=instrument_id,
                    fingerprint=digest,
                    observed_at=datetime.now(UTC),
                    data=data,
                )
                .on_conflict_do_nothing(constraint="uq_valuation_observation")
                .returning(ValuationObservation.id)
            )
        ).scalar_one_or_none()
        await self.session.commit()
        return {"inserted": identifier is not None, "id": identifier}

    async def detail(self, instrument_id: UUID):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            return None
        rows = (
            (
                await self.session.execute(
                    select(ValuationObservation)
                    .where(ValuationObservation.instrument_id == instrument_id)
                    .order_by(ValuationObservation.observed_at.desc(), ValuationObservation.id)
                    .limit(21)
                )
            )
            .scalars()
            .all()
        )
        price = await MarketDataService(self.session).latest_price(instrument_id)
        latest = rows[0] if rows else None
        calculation = calculate_valuation(
            instrument, price, latest.data if latest else None, datetime.now(UTC)
        )
        if latest and len([r for r in rows if r.observed_at == latest.observed_at]) > 1:
            calculation = {
                "status": "blocked",
                "reasons": ["Observations simultanées ambiguës."],
                "pe": None,
                "earnings_yield_percent": None,
                "reference_comparison": None,
                "normalized_price": None,
            }
        return {
            "calculation": calculation,
            "instrument": {
                "currency": instrument.currency,
                "quote_multiplier": instrument.quote_multiplier,
            },
            "price": {
                "close": price.close,
                "date": price.session_date,
                "source_url": price.source_url,
                "quote_context": price.quote_context,
            }
            if price
            else None,
            "observation": {"id": latest.id, "observed_at": latest.observed_at, **latest.data}
            if latest
            else None,
            "history": [{"id": r.id, "observed_at": r.observed_at, **r.data} for r in rows[:20]],
            "history_limited": len(rows) > 20,
            "notice": "PER sur BPA annuel GAAP dilué déclaré compatible "
            "avec ce titre et cette séance. "
            "Preuves fournies manuellement, sans validation automatique de leur contenu. "
            "Le rendement bénéficiaire est un ratio comptable, pas un gain ou dividende prévu. "
            "Aucun seuil universel de prix élevé/faible ; référence sourcée nécessaire. "
            "Les BPA SEC d’émetteur ne sont pas attribués automatiquement à cette cotation.",
        }
