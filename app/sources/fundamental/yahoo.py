import pandas as pd
import yfinance as yf

from app.sources.fundamental.base import FundamentalSourceBase


def _to_date(ts):
    try:
        return pd.Timestamp(ts).date()
    except Exception:
        return None


def _get(df, col, *keys):
    """Extrae un float de df.loc[key, col] probando múltiples nombres de fila."""
    if df is None or df.empty:
        return None
    for key in keys:
        if key in df.index:
            try:
                val = df.loc[key, col]
                return None if pd.isna(val) else float(val)
            except Exception:
                continue
    return None


class YahooFundamentalSource(FundamentalSourceBase):
    SOURCE_NAME = "Yahoo Finance"

    def fetch_quarterly(self, ticker: str) -> list[dict]:
        t = yf.Ticker(ticker)

        try:
            fin = t.quarterly_financials
        except Exception:
            fin = pd.DataFrame()

        try:
            bs = t.quarterly_balance_sheet
        except Exception:
            bs = pd.DataFrame()

        try:
            cf = t.quarterly_cashflow
        except Exception:
            cf = pd.DataFrame()

        # EPS trimestral
        eps_map: dict = {}
        try:
            eq = t.quarterly_earnings
            if eq is not None and not eq.empty:
                for idx, row in eq.iterrows():
                    d = _to_date(idx)
                    if d:
                        eps_map[d] = {
                            "actual":    float(row.get("Earnings", float("nan"))) if not pd.isna(row.get("Earnings", float("nan"))) else None,
                            "estimated": None,
                        }
        except Exception:
            pass

        if fin.empty:
            return []

        quarters = []
        for col in fin.columns:
            d = _to_date(col)
            if d is None:
                continue

            bs_col = col if (not bs.empty and col in bs.columns) else None
            cf_col = col if (not cf.empty and col in cf.columns) else None

            row = {
                "period_date":      d,
                "revenue":          _get(fin, col, "Total Revenue"),
                "gross_profit":     _get(fin, col, "Gross Profit"),
                "operating_income": _get(fin, col, "Operating Income", "EBIT"),
                "net_income":       _get(fin, col, "Net Income"),
                "ebitda":           _get(fin, col, "EBITDA"),
                "total_debt":       _get(bs, bs_col, "Total Debt", "Long Term Debt And Capital Lease Obligation") if bs_col else None,
                "equity":           _get(bs, bs_col, "Stockholders Equity", "Common Stock Equity") if bs_col else None,
                "shares":           _get(bs, bs_col, "Ordinary Shares Number", "Share Issued") if bs_col else None,
                "fcf":              _get(cf, cf_col, "Free Cash Flow") if cf_col else None,
                "operating_cf":     _get(cf, cf_col, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities") if cf_col else None,
                "eps_actual":       eps_map.get(d, {}).get("actual"),
                "eps_estimated":    eps_map.get(d, {}).get("estimated"),
            }
            quarters.append(row)

        return quarters
