import dash_bootstrap_components as dbc
from flask_login import current_user


def build_navbar() -> dbc.Navbar:

    nav_items = [
        dbc.NavItem(dbc.NavLink("Screener", href="/screener")),
        dbc.NavItem(dbc.NavLink("Gráfico técnico", href="/chart")),
    ]

    if current_user.is_authenticated and current_user.is_admin:
        nav_items += [
            dbc.DropdownMenu(
                label="Activos",
                children=[
                    dbc.DropdownMenuItem("Gestión de activos", href="/assets"),
                    dbc.DropdownMenuItem("Importar activos",   href="/assets/import"),
                ],
                nav=True, in_navbar=True,
            ),
            dbc.DropdownMenu(
                label="Precios",
                children=[
                    dbc.DropdownMenuItem("Visualizador de precios",   href="/price-viewer"),
                    dbc.DropdownMenuItem("Actualización de precios",  href="/prices"),
                ],
                nav=True, in_navbar=True,
            ),
            dbc.DropdownMenu(
                label="Datos de mercado",
                children=[
                    dbc.DropdownMenuItem("Eventos de mercado",   href="/admin/events"),
                    dbc.DropdownMenuItem(divider=True),
                    dbc.DropdownMenuItem("Países",               href="/admin/countries"),
                    dbc.DropdownMenuItem("Monedas",              href="/admin/currencies"),
                    dbc.DropdownMenuItem("Mercados",             href="/admin/markets"),
                    dbc.DropdownMenuItem("Tipos de instrumento", href="/admin/instrument-types"),
                    dbc.DropdownMenuItem("Sectores",             href="/admin/sectors"),
                    dbc.DropdownMenuItem("Industrias",           href="/admin/industries"),
                    dbc.DropdownMenuItem("Fuentes de precios",   href="/admin/price-sources"),
                ],
                nav=True, in_navbar=True,
            ),
            dbc.DropdownMenu(
                label="Administración",
                children=[
                    dbc.DropdownMenuItem("Usuarios", href="/admin/users"),
                ],
                nav=True, in_navbar=True,
            ),
        ]
    else:
        # Analista: solo puede ver precios
        nav_items.append(
            dbc.NavItem(dbc.NavLink("Precios", href="/price-viewer"))
        )

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
