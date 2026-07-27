"""
Componente ABM genérico reutilizable.
Genera el layout de tabla + modal para cualquier entidad de referencia.
Los callbacks se registran individualmente en cada módulo de callback.
"""
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import dcc, html
from app.components.grids import (
    DEFAULT_COL_DEF, THEME_CLASS, grid_options, multi_selection, to_column_defs,
)
from app.components.help import help_link


def make_abm_layout(
    entity_id: str,
    title: str,
    table_columns: list[dict],
    form_fields: list,
    admin_only: bool = True,
    help_slug: str | None = None,
) -> html.Div:
    """
    Genera un layout ABM estándar.

    entity_id   : identificador único (usado como prefijo en los IDs de Dash)
    title       : título de la página
    table_columns: columnas de la grilla; acepta el formato viejo {name, id}
                  además del de ag-grid (ver `grids.to_column_defs`)
    form_fields : lista de componentes dbc.FormGroup/Row para el modal
    help_slug   : sección del manual de esta pantalla; agrega el ícono «?»
                  al lado del título. Sin él, la pantalla no ofrece ayuda.
    """
    encabezado = [title, " ", help_link(help_slug)] if help_slug else title
    return html.Div(
        [
            dcc.Store(id=f"{entity_id}-editing-id", data=None),
            html.Div(
                [
                    html.H3(encabezado, className="d-inline-block me-3"),
                    dbc.Button(
                        "+ Nuevo",
                        id=f"{entity_id}-btn-add",
                        color="primary",
                        size="sm",
                    ),
                ],
                className="d-flex align-items-center mb-3",
            ),
            dbc.Alert(id=f"{entity_id}-alert", is_open=False, dismissable=True),
            html.Div(
                [
                    dbc.Button(
                        "Editar",
                        id=f"{entity_id}-btn-edit",
                        color="secondary",
                        size="sm",
                        disabled=True,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Eliminar",
                        id=f"{entity_id}-btn-delete",
                        color="danger",
                        size="sm",
                        disabled=True,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Sel. todos",
                        id=f"{entity_id}-btn-select-all",
                        color="outline-secondary",
                        size="sm",
                        className="me-1",
                    ),
                    dbc.Button(
                        "Desel. todos",
                        id=f"{entity_id}-btn-deselect-all",
                        color="outline-secondary",
                        size="sm",
                    ),
                ],
                className="mb-2",
            ),
            dag.AgGrid(
                id=f"{entity_id}-table",
                columnDefs=to_column_defs(table_columns),
                rowData=[],
                className=THEME_CLASS,
                style={"height": "calc(100vh - 330px)", "width": "100%"},
                defaultColDef=DEFAULT_COL_DEF,
                # Identidad por id: los callbacks del ABM reescriben las filas
                # después de cada alta/baja y sin esto se pierde la selección.
                getRowId="params.data.id",
                dashGridOptions=grid_options(rowSelection=multi_selection()),
            ),
            # Modal formulario
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle(id=f"{entity_id}-modal-title")),
                    dbc.ModalBody(
                        (form_fields if isinstance(form_fields, list) else [form_fields]) + [
                            dbc.Alert(
                                id=f"{entity_id}-modal-error",
                                is_open=False,
                                color="danger",
                                className="mt-2 mb-0 small py-1",
                            ),
                        ]
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Guardar",
                                id=f"{entity_id}-btn-save",
                                color="primary",
                            ),
                            dbc.Button(
                                "Cancelar",
                                id=f"{entity_id}-btn-cancel",
                                color="secondary",
                                className="ms-2",
                            ),
                        ]
                    ),
                ],
                id=f"{entity_id}-modal",
                is_open=False,
            ),
            # Modal confirmación borrado
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Confirmar eliminación")),
                    dbc.ModalBody(
                        id=f"{entity_id}-confirm-body",
                        children="¿Confirmás la eliminación del registro?",
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Sí, eliminar",
                                id=f"{entity_id}-btn-confirm-delete",
                                color="danger",
                            ),
                            dbc.Button(
                                "Cancelar",
                                id=f"{entity_id}-btn-cancel-delete",
                                color="secondary",
                                className="ms-2",
                            ),
                        ]
                    ),
                ],
                id=f"{entity_id}-confirm-modal",
                is_open=False,
            ),
        ]
    )
