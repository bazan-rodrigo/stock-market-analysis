"""
Intenta encontrar el endpoint de riesgo país de Ámbito de dos formas:

Modo 1 (automático): Prueba candidatos con headers de browser real.
Modo 2 (Playwright): Abre el browser, captura la llamada de red real.

Ejecutar modo 1:
    python scripts/find_ambito_endpoint.py

Ejecutar modo 2 (requiere: pip install playwright && playwright install chromium):
    python scripts/find_ambito_endpoint.py --playwright
"""

import sys
import json
sys.stdout.reconfigure(encoding="utf-8")
import requests

BASE = "https://mercados.ambito.com"
DESDE = "2024-01-01"
HASTA = "2024-06-01"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9",
    "Referer": "https://www.ambito.com/contenidos/riesgo-pais-historico.html",
    "Origin": "https://www.ambito.com",
}

# Candidatos que aún no probamos con Referer
CANDIDATES = [
    f"{BASE}/riesgo/pais/grafico/{DESDE}/{HASTA}",
    f"{BASE}/riesgo/argentina/grafico/{DESDE}/{HASTA}",
    f"{BASE}/riesgo-pais/grafico/{DESDE}/{HASTA}",
    f"{BASE}/indices/riesgo-pais/grafico/{DESDE}/{HASTA}",
    f"{BASE}/embi/argentina/grafico/{DESDE}/{HASTA}",
    f"{BASE}/riesgo/pais/variacion",
    f"{BASE}/riesgo/argentina/variacion",
    f"{BASE}/riesgo-pais/variacion",
    f"{BASE}/indice/riesgo-pais/variacion",
    f"{BASE}/embi/argentina/variacion",
    f"{BASE}/riesgo_pais/grafico/{DESDE}/{HASTA}",
    f"{BASE}/riesgo_pais/variacion",
    f"{BASE}/riesgo/pais/historico/{DESDE}/{HASTA}",
    f"{BASE}/riesgo-pais/historico/{DESDE}/{HASTA}",
    # Variantes con IDs numéricos (como usan algunos CMS)
    f"{BASE}/indice/1/grafico/{DESDE}/{HASTA}",
    f"{BASE}/indice/2/grafico/{DESDE}/{HASTA}",
    f"{BASE}/indice/3/grafico/{DESDE}/{HASTA}",
    # Variantes con "embi" como subtipo del dólar pattern
    f"{BASE}/embi/1/grafico/{DESDE}/{HASTA}",
    f"{BASE}/embi/pais/variacion",
    # Ambito data API
    f"https://data.ambito.com/api/riesgo-pais/historico?desde={DESDE}&hasta={HASTA}",
    f"https://data.ambito.com/riesgo-pais/grafico/{DESDE}/{HASTA}",
    # Posible endpoint en www.ambito.com
    f"https://www.ambito.com/api/riesgo-pais/historico?desde={DESDE}&hasta={HASTA}",
    f"https://www.ambito.com/api/indices/embi?desde={DESDE}&hasta={HASTA}",
    # Variantes con "pais" sin tilde
    f"{BASE}/riesgo/pais/grafico/{DESDE}/{HASTA}",
    f"{BASE}/risgo/pais/grafico/{DESDE}/{HASTA}",
]


def modo_requests():
    print("=== MODO 1: requests con headers de browser ===\n")
    session = requests.Session()

    # Primero cargamos la página principal para obtener cookies
    try:
        session.get(
            "https://www.ambito.com/contenidos/riesgo-pais-historico.html",
            headers=HEADERS,
            timeout=10,
        )
        print("  Cookies obtenidas de la página principal")
    except Exception as e:
        print(f"  Warning al cargar página principal: {e}")

    found = []
    for url in CANDIDATES:
        try:
            r = session.get(url, headers=HEADERS, timeout=8)
            if r.ok:
                try:
                    data = r.json()
                    print(f"\n  ✓ ENCONTRADO: {url}")
                    print(f"    Tipo: {type(data).__name__}")
                    preview = json.dumps(data)[:300]
                    print(f"    Preview: {preview}")
                    found.append(url)
                except Exception:
                    if len(r.text) > 100:
                        print(f"\n  ✓ OK (no-JSON): {url}")
                        print(f"    Preview: {r.text[:200]}")
                        found.append(url)
                    else:
                        print(f"  200 vacío: {url}")
            else:
                path = url.replace(BASE, "").replace("https://www.ambito.com", "")
                print(f"  {r.status_code} {path}")
        except Exception as e:
            print(f"  ERR {url}: {e}")

    if found:
        print(f"\n=== ENDPOINTS ENCONTRADOS ===")
        for u in found:
            print(f"  {u}")
    else:
        print("\n  ✗ Ningún endpoint respondió.")
        print("  → Ejecutá con --playwright para captura real de red")


def modo_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright no instalado.")
        print("Instalá con: pip install playwright && playwright install chromium")
        return

    print("=== MODO 2: Playwright — captura de red real ===\n")
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def on_request(request):
            url = request.url
            if "mercados.ambito" in url or (
                "ambito" in url and any(
                    k in url for k in ["riesgo", "embi", "grafico", "historico", "indice"]
                )
            ):
                captured.append(url)
                print(f"  [NET] {request.method} {url}")

        page.on("request", on_request)

        print("  Cargando página histórica de Ámbito...")
        page.goto(
            "https://www.ambito.com/contenidos/riesgo-pais-historico.html",
            wait_until="networkidle",
            timeout=30000,
        )

        # Intentar rellenar el formulario de fechas y hacer click en VER DATOS
        try:
            page.fill('input[type="date"]:first-of-type', "2024-01-01")
            page.fill('input[type="date"]:last-of-type', "2024-06-01")
            page.click("button:has-text('VER DATOS')")
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            print(f"  No se pudo interactuar con el formulario: {e}")
            print("  (Revisando URLs capturadas igual...)")

        browser.close()

    if captured:
        print("\n=== URLS CAPTURADAS ===")
        for u in set(captured):
            print(f"  {u}")
    else:
        print("\n  ✗ No se capturó ninguna URL de Ámbito relevante.")


if __name__ == "__main__":
    if "--playwright" in sys.argv:
        modo_playwright()
    else:
        modo_requests()
