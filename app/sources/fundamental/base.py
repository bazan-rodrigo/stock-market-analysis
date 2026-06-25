from abc import ABC, abstractmethod


class FundamentalSourceBase(ABC):
    SOURCE_NAME: str = ""

    @abstractmethod
    def fetch_quarterly(self, ticker: str) -> list[dict]:
        """
        Devuelve lista de dicts, uno por trimestre, con las claves:
          period_date, revenue, gross_profit, operating_income, net_income,
          ebitda, total_debt, equity, shares, fcf, operating_cf,
          eps_actual, eps_estimated
        Lanza excepción si falla la consulta.
        """
        ...
