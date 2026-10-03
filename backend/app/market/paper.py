from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Fill:
    cash: Decimal
    quantity: int
    cost_basis: Decimal
    fee: Decimal
    realized_pnl: Decimal


def calculate_fill(
    *,
    cash: Decimal,
    held: int,
    cost_basis: Decimal,
    side: str,
    quantity: int,
    price: Decimal,
    fee_bps: Decimal,
) -> Fill:
    if quantity <= 0 or price <= 0 or not price.is_finite():
        raise ValueError("Quantité ou cours invalide.")
    gross = money(price * quantity)
    fee = money(gross * fee_bps / Decimal("10000"))
    if side == "buy":
        if gross == 0:
            raise ValueError("Montant d'achat inférieur à un centime : augmenter la quantité.")
        debit = gross + fee
        if debit > cash:
            raise ValueError("Capital disponible insuffisant, frais inclus.")
        return Fill(cash - debit, held + quantity, cost_basis + debit, fee, Decimal("0"))
    if side != "sell" or quantity > held:
        raise ValueError("Vente refusée : titres détenus insuffisants. Pas de vente à découvert.")
    allocation = cost_basis if quantity == held else money(cost_basis * quantity / held)
    proceeds = gross - fee
    return Fill(
        cash + proceeds, held - quantity, cost_basis - allocation, fee, proceeds - allocation
    )


def check_concentration(position_value: Decimal, portfolio_value: Decimal, maximum: Decimal):
    if portfolio_value <= 0 or position_value * 100 > portfolio_value * maximum:
        raise ValueError("La position dépasse la concentration maximale du portefeuille.")
