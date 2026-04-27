import dash_bootstrap_components as dbc
from flask_login import current_user


def build_navbar() -> dbc.Navbar:

    analisis_menu = dbc.DropdownMenu(
        label="Análisis",
        children=[
            dbc.DropdownMenuItem("Gráfico técnico",    href="/chart"),
            dbc.DropdownMenuItem("Screener",           href="/screener"),
            dbc.DropdownMenuItem("Mapa de Mercado",    href="/market-map"),
            dbc.DropdownMenuItem("Rotación Relativa",  href="/rrg"),
            dbc.DropdownMenuItem("Evolución",          href="/evolucion"),
            dbc.DropdownMenuItem("Análisis de Pares",  href="/par"),
            dbc.DropdownMenuItem(divider=True),
            dbc.DropdownMenuItem("Screener de Señales", href="/senales"),
        ],
        nav=True, in_navbar=True,
    )

    if current_user.is_authenticated and current_user.is_admin:
        nav_items = [
            analisis_menu,
            dbc.DropdownMenu(
                label="Activos",
                children=[
                    dbc.DropdownMenuItem("Gestión de activos", href="/assets"),
                    dbc.DropdownMenuItem("Importar activos",   href="/assets/import"),
                    dbc.DropdownMenuItem(divider=True),
                    dbc.DropdownMenuItem("Activos sintéticos", href="/admin/synthetic"),
                    dbc.DropdownMenuItem("Activos en Divisa",  href="/admin/ars-conversion"),
                ],
                nav=True, in_navbar=True,
            ),
            dbc.DropdownMenu(
                label="Precios",
                children=[
                    dbc.DropdownMenuItem("Visualizador de precios",  href="/price-viewer"),
                    dbc.DropdownMenuItem("Actualización de precios", href="/prices"),
                ],
                nav=True, in_navbar=True,
            ),
            dbc.DropdownMenu(
                label="Configuración",
                children=[
                    dbc.DropdownMenuItem("Mapper de catálogo",    href="/admin/catalog-mapper"),
                    dbc.DropdownMenuItem("Régimen de Tendencia",  href="/admin/regime-config"),
                    dbc.DropdownMenuItem("Volatilidad ATR",       href="/admin/volatility-config"),
                    dbc.DropdownMenuItem("Drawdowns",             href="/admin/drawdown-config"),
                    dbc.DropdownMenuItem("Soporte / Resistencia", href="/admin/sr-config"),
                    dbc.DropdownMenuItem(divider=True),
                    dbc.DropdownMenuItem("Señales",    href="/admin/signals"),
                    dbc.DropdownMenuItem("Estrategias",href="/admin/strategies"),
                ],
                nav=True, in_navbar=True,
            ),
            dbc.DropdownMenu(
                label="Administración",
                children=[
                    dbc.DropdownMenuItem("Eventos de mercado",   href="/admin/events"),
                    dbc.DropdownMenuItem("Importar eventos",     href="/admin/events/import"),
                    dbc.DropdownMenuItem(divider=True),
                    dbc.DropdownMenuItem("Países",               href="/admin/countries"),
                    dbc.DropdownMenuItem("Monedas",              href="/admin/currencies"),
                    dbc.DropdownMenuItem("Mercados",             href="/admin/markets"),
                    dbc.DropdownMenuItem("Tipos de instrumento", href="/admin/instrument-types"),
                    dbc.DropdownMenuItem("Sectores",             href="/admin/sectors"),
                    dbc.DropdownMenuItem("Industrias",           href="/admin/industries"),
                    dbc.DropdownMenuItem("Fuentes de precios",   href="/admin/price-sources"),
                    dbc.DropdownMenuItem(divider=True),
                    dbc.DropdownMenuItem("Usuarios",             href="/admin/users"),
                    dbc.DropdownMenuItem("Scheduler",            href="/admin/scheduler"),
                    dbc.DropdownMenuItem("Limpieza de datos",    href="/admin/cleanup"),
                    dbc.DropdownMenuItem(divider=True),
                    dbc.DropdownMenuItem("Consola SQL",          href="/admin/sql"),
                ],
                nav=True, in_navbar=True,
            ),
        ]
    else:
        nav_items = [
            analisis_menu,
            dbc.NavItem(dbc.NavLink("Precios", href="/price-viewer")),
        ]

    username = current_user.username if current_user.is_authenticated else ""
    user_menu = dbc.DropdownMenu(
        label=username,
        children=[dbc.DropdownMenuItem("Cerrar sesión", href="/logout", external_link=True)],
        nav=True, in_navbar=True, align_end=True,
    )

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand("Stock Analysis", href="/"),
            dbc.NavbarToggler(id="navbar-toggler"),
            dbc.Collapse(
                dbc.Nav(nav_items + [user_menu], className="ms-auto", navbar=True),
                id="navbar-collapse",
                navbar=True,
            ),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-3",
    )
