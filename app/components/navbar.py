import dash_bootstrap_components as dbc
from dash import html
from flask_login import current_user


def build_navbar() -> dbc.Navbar:
    """Construye la barra de navegación adaptada al rol del usuario actual."""

    admin_items = [
        dbc.DropdownMenuItem("Usuarios", href="/admin/users"),
        dbc.DropdownMenuItem(divider=True),
        dbc.DropdownMenuItem("Países", href="/admin/countries"),
        dbc.DropdownMenuItem("Monedas", href="/admin/currencies"),
        dbc.DropdownMenuItem("Mercados", href="/admin/markets"),
        dbc.DropdownMenuItem("Tipos de instrumento", href="/admin/instrument-types"),
        dbc.DropdownMenuItem("Sectores", href="/admin/sectors"),
        dbc.DropdownMenuItem("Industrias", href="/admin/industries"),
        dbc.DropdownMenuItem("Fuentes de precios", href="/admin/price-sources"),
        dbc.DropdownMenuItem(divider=True),
        dbc.DropdownMenuItem("Gestión de activos", href="/assets"),
        dbc.DropdownMenuItem("Importar activos", href="/assets/import"),
        dbc.DropdownMenuItem("Actualización de precios", href="/prices"),
    ]

    nav_items = [
        dbc.NavItem(dbc.NavLink("Screener", href="/screener")),
        dbc.NavItem(dbc.NavLink("Gráfico técnico", href="/chart")),
    ]

    if current_user.is_authenticated and current_user.is_admin:
        nav_items.append(
            dbc.DropdownMenu(
                label="Administración",
                children=admin_items,
                nav=True,
                in_navbar=True,
            )
        )

    username = current_user.username if current_user.is_authenticated else ""
    user_menu = dbc.DropdownMenu(
        label=username,
        children=[
            dbc.DropdownMenuItem("Cerrar sesión", href="/logout"),
        ],
        nav=True,
        in_navbar=True,
        align_end=True,
    )

    return dbc.Navbar(
        dbc.Container(
            [
                dbc.NavbarBrand("Stock Analysis", href="/"),
                dbc.NavbarToggler(id="navbar-toggler"),
                dbc.Collapse(
                    dbc.Nav(nav_items + [user_menu], className="ms-auto", navbar=True),
                    id="navbar-collapse",
                    navbar=True,
                ),
            ],
            fluid=True,
        ),
        color="dark",
        dark=True,
        className="mb-3",
    )
