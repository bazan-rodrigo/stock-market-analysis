"""
Testea distintas fuentes de riesgo país (EMBI) Argentina.

Ejecutar: python scripts/test_embi_sources.py

PASO PREVIO para Ámbito:
  1. Abrí https://www.ambito.com/contenidos/riesgo-pais-historico.html
  2. F12 → Network → filtrar XHR/Fetch
  3. Seleccioná un rango de fechas y hacé click en "VER DATOS"
  4. Copiá la URL que aparece y pegala en AMBITO_ENDPOINT abajo
"""

import sys
import requests
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ── Pegá acá el endpoint que encontrés con DevTools ──────────────────────────
AMBITO_ENDPOINT = "https://mercados.ambito.com/riesgopais/historico-general"
# ─────────────────────────────────────────────────────────────────────────────

FRED_API_KEY = '8d0125e2941bac4d9a50cf8db777f0c7'  # Registrá gratis en https://fred.stlouisfed.org/docs/api/api_key.html


def print_result(df):
    if df is None or df.empty:
        print(f"  ✗ Sin datos")
        return
    print(f"  Registros : {len(df)}")
    print(f"  Desde     : {df['fecha'].min()}")
    print(f"  Hasta     : {df['fecha'].max()}")
    print(f"  Muestra   : {df.head(2).to_dict('records')}")


def test_ambito(desde="1994-01-01", hasta="2026-06-26"):
    if not AMBITO_ENDPOINT:
        print("  ✗ AMBITO_ENDPOINT no configurado (ver instrucciones arriba)")
        return

    # Probamos patrón con y sin fechas
    for url in [
        f"{AMBITO_ENDPOINT}/{desde}/{hasta}",
        AMBITO_ENDPOINT,
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.ok:
                raw = r.json()
                if isinstance(raw, list) and len(raw) > 1:
                    header = raw[0]
                    rows = raw[1:]
                    df = pd.DataFrame(rows, columns=header)
                    df.columns = ["fecha", "valor"]
                    df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True)
                    print(f"  ✓ URL: {url}")
                    print_result(df)
                    return
        except Exception as e:
            print(f"  Error: {e}")
    print("  ✗ Ningún endpoint funcionó")


def test_fred(desde="1993-01-01"):
    """Serie WEMBIARG — semanal desde ~1998."""
    if not FRED_API_KEY:
        print("  ✗ FRED_API_KEY no configurado")
        print("    → Registrá gratis: https://fred.stlouisfed.org/docs/api/api_key.html")
        return
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=WEMBIARG&api_key={FRED_API_KEY}&file_type=json"
        f"&observation_start={desde}"
    )
    try:
        r = requests.get(url, timeout=15)
        if r.ok:
            obs = r.json().get("observations", [])
            df = pd.DataFrame(obs)
            df = df[df["value"] != "."].copy()
            df["fecha"] = pd.to_datetime(df["date"])
            df["valor"] = df["value"].astype(float)
            df = df[["fecha", "valor"]]
            print(f"  ✓ Frecuencia: semanal")
            print_result(df)
        else:
            print(f"  ✗ HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"  Error: {e}")


def test_datos_gob_ar():
    """
    Portal datos.gob.ar — la búsqueda por 'EMBI' devuelve 0 resultados.
    No tienen la serie. Se confirma con los términos más generales.
    """
    search_url = "https://apis.datos.gob.ar/series/api/search/"
    for term in ["EMBI", "riesgo pais", "spread soberano"]:
        params = {"q": term, "limit": 5}
        try:
            r = requests.get(search_url, params=params, headers=HEADERS, timeout=10)
            if r.ok:
                data = r.json()
                count = data.get("count", 0)
                results = data.get("data", [])
                if results:
                    s = results[0]
                    f = s.get("field", {})
                    print(f"  '{term}': {count} resultados — mejor match:")
                    print(f"    ID: {f.get('id')} | {f.get('description','')[:60]}")
                    print(f"    Desde: {f.get('time_index_start')} → {f.get('time_index_end')}")
                else:
                    print(f"  '{term}': 0 resultados")
            else:
                print(f"  ✗ HTTP {r.status_code}")
        except Exception as e:
            print(f"  Error con '{term}': {e}")
    print("  → datos.gob.ar NO tiene serie EMBI")


def test_bcra():
    """
    API del BCRA — busca la variable EMBI entre las principales variables.
    """
    url = "https://api.bcra.gob.ar/estadisticas/v3.0/Monetaria"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if r.ok:
            variables = r.json().get("results", [])
            embi_vars = [v for v in variables if "embi" in str(v).lower() or "riesgo" in str(v).lower()]
            if embi_vars:
                print(f"  ✓ Variables EMBI/Riesgo encontradas: {embi_vars}")
            else:
                print(f"  ✗ BCRA no publica EMBI (confirmado). Variables disponibles: {len(variables)}")
        else:
            print(f"  ✗ HTTP {r.status_code}")
    except Exception as e:
        print(f"  Error: {e}")


def test_imf():
    """FMI DataMapper — spread soberano anual."""
    url = "https://www.imf.org/external/datamapper/api/v1/FDSB@IFS/ARG"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.ok:
            valores = r.json().get("values", {}).get("FDSB", {}).get("ARG", {})
            if valores:
                df = pd.DataFrame(list(valores.items()), columns=["fecha", "valor"])
                df["fecha"] = pd.to_datetime(df["fecha"])
                print(f"  ✓ Frecuencia: anual")
                print_result(df)
            else:
                print("  ✗ Sin datos para Argentina")
        else:
            print(f"  ✗ HTTP {r.status_code}")
    except Exception as e:
        print(f"  Error: {e}")


def test_ambito_probe():
    """
    Prueba variantes del endpoint de Ámbito para riesgo país
    usando el patrón confirmado: /categoria/tipo/grafico/{desde}/{hasta}
    """
    desde, hasta = "2024-01-01", "2024-06-01"
    candidatos = [
        f"https://mercados.ambito.com/riesgo/pais/grafico/{desde}/{hasta}",
        f"https://mercados.ambito.com/riesgo/argentina/grafico/{desde}/{hasta}",
        f"https://mercados.ambito.com/riesgo-pais/grafico/{desde}/{hasta}",
        f"https://mercados.ambito.com/indices/riesgo-pais/grafico/{desde}/{hasta}",
        f"https://mercados.ambito.com/embi/pais/grafico/{desde}/{hasta}",
        f"https://mercados.ambito.com/embi/argentina/grafico/{desde}/{hasta}",
        f"https://mercados.ambito.com/indice/riesgo/grafico/{desde}/{hasta}",
        f"https://mercados.ambito.com/bono/embi/grafico/{desde}/{hasta}",
    ]
    for url in candidatos:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            status = r.status_code
            if r.ok:
                print(f"  ✓ ENCONTRADO: {url}")
                raw = r.json()
                print(f"    Respuesta: {str(raw)[:200]}")
                return url
            else:
                print(f"  {status} {url.split('mercados.ambito.com')[1]}")
        except Exception as e:
            print(f"  ERR {url.split('mercados.ambito.com')[1]} — {e}")
    return None


if __name__ == "__main__":
    requests.packages.urllib3.disable_warnings()

    print("=" * 65)
    print("TEST DE FUENTES DE RIESGO PAÍS ARGENTINA (EMBI)")
    print("=" * 65)

    print("\n1. ÁMBITO — Sondeo de endpoints posibles")
    found = test_ambito_probe()

    print("\n2. ÁMBITO — Carga con endpoint configurado")
    test_ambito()

    print("\n3. FRED (Federal Reserve St. Louis — WEMBIARG semanal)")
    test_fred()

    print("\n4. DATOS.GOB.AR (catálogo MECON)")
    test_datos_gob_ar()

    print("\n5. BCRA API")
    test_bcra()

    print("\n6. FMI DataMapper (anual)")
    test_imf()

    print()
