from abc import ABC, abstractmethod


class FundamentalSourceBase(ABC):
    SOURCE_NAME: str = ""

    @abstractmethod
    def fetch_quarterly(self, ticker: str) -> list[dict]:
        """
        Devuelve lista de dicts, uno por trimestre. Claves obligatorias:
          period_date, revenue, gross_profit, operating_income, net_income,
          ebitda, total_debt, equity, shares, fcf, operating_cf,
          eps_actual, eps_estimated

        Claves opcionales (mejoran precisión del ROIC si están disponibles):
          nopat                — Net Operating Profit After Tax del trimestre
          invested_capital_avg — Capital invertido promedio del período
                                 (inicio + fin) / 2

        Si la fuente provee nopat e invested_capital_avg, el sistema usará
        ROIC = NOPAT TTM / IC promedio en lugar de la aproximación
        Net Income TTM / (Equity + Total Debt).

        Lanza excepción si falla la consulta.
        """
        ...
