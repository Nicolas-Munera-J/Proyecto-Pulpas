"""Formato de presentación para las plantillas."""
from decimal import ROUND_HALF_UP, Decimal


def moneda(valor) -> str:
    """Pesos colombianos: separador de miles con punto y sin decimales.
    Ejemplo: 44000 -> "$ 44.000"."""
    entero = Decimal(str(valor or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return "$ " + f"{int(entero):,}".replace(",", ".")
