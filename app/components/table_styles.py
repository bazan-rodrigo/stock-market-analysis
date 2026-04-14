"""Estilos dark mode compartidos para dash_table.DataTable."""

HEADER = {
    "fontWeight": "bold",
    "backgroundColor": "#2c2c2c",
    "color": "#dee2e6",
    "border": "1px solid #444",
}

DATA = {
    "backgroundColor": "#1e1e1e",
    "color": "#dee2e6",
    "border": "1px solid #333",
}

CELL = {
    "textAlign": "left",
    "padding": "4px 10px",
    "fontSize": "0.82rem",
    "border": "1px solid #333",
}

SELECTED_ROW = [
    {
        "if": {"state": "selected"},
        "backgroundColor": "#1a4a6e",
        "color": "#fff",
        "border": "1px solid #1a4a6e",
    }
]
