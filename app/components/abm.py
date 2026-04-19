"""
Componente ABM genérico reutilizable.
Genera el layout de tabla + modal para cualquier entidad de referencia.
Los callbacks se registran individualmente en cada módulo de callback.
"""
import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html
from app.components.table_styles import FILTER, HEADER, DATA, CELL, SELECTED_ROW


def make_abm_layout(
    entity_id: str,
    title: str,
    table_columns: list[dict],
    form_fields: list,
    admin_only: bool = True,
) -> html.Div:
    """
    Genera un layout ABM estándar.

    entity_id   : identificador único (usado como prefijo en los IDs de Dash)
    title       : título de la página
    table_columns: lista de dicts {name, id} para el DataTable
    form_fields : lista de componentes dbc.FormGroup/Row para el modal
    """
    return html.Div(
        [
            dcc.Store(id=f"{entity_id}-editing-id", data=None),
            html.Div(
                [
                    html.H3(title, className="d-inline-block me-3"),
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
            dash_table.DataTable(
                id=f"{entity_id}-table",
                columns=table_columns,
                data=[],
                row_selectable="multi",
                selected_rows=[],
                style_table={"overflowX": "auto"},
                style_header=HEADER,
                style_data=DATA,
                style_cell=CELL,
                style_filter=FILTER,
                style_data_conditional=SELECTED_ROW,
                page_size=25,
                sort_action="native",
                filter_action="native",
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
