"""
Visibilidad y permisos de señales y estrategias.

Modelo (migración 0065):
  owner_id   — quién la creó. Controla la EDICIÓN: solo el dueño o un
               admin editan/borran/publican. NULL = sin dueño (lo
               importado/creado antes de la 0065) → edita solo el admin.
               No cambia nunca al publicar/despublicar.
  is_public  — solo VISIBILIDAD: pública la ven todos (incluido quien no
               tiene usuario propio); privada, solo su dueño y el admin.

Regla de referencias (composites, componentes de estrategia, operandos
señal del filtro de elegibilidad): una definición PÚBLICA solo puede
referenciar señales públicas; una PRIVADA puede referenciar públicas +
las del mismo dueño. Así una señal privada nunca se filtra a otros
usuarios a través de algo que sí ven.

El pipeline de cálculo (señales, estrategias, scheduler) ignora ambos
campos: calcula TODO. La visibilidad es de definiciones y pantallas, no
de valores.
"""

# ── Lógica pura (testeable sin BD) ────────────────────────────────────────────

def can_view(owner_id, is_public, user_id, is_admin) -> bool:
    """El usuario ve la definición: pública, propia, o es admin."""
    if is_public or is_admin:
        return True
    return user_id is not None and owner_id == user_id


def can_edit(owner_id, user_id, is_admin) -> bool:
    """El usuario edita/borra/publica: es admin o es el dueño.
    owner_id NULL (sin dueño) → solo admin."""
    if is_admin:
        return True
    return user_id is not None and owner_id is not None and owner_id == user_id


def can_reference(parent_owner_id, parent_is_public,
                  ref_owner_id, ref_is_public) -> bool:
    """La definición padre puede referenciar a la señal ref sin filtrar
    una privada a quien no debe verla."""
    if parent_is_public:
        return bool(ref_is_public)
    return bool(ref_is_public) or (
        parent_owner_id is not None and ref_owner_id == parent_owner_id)


def parse_publica(value) -> bool:
    """Columna `publica` de los xlsx de import: sí/no. Ausente o vacía =
    pública (compatibilidad con packs anteriores a la columna)."""
    if value is None:
        return True
    text = str(value).strip().lower()
    if text in ("", "si", "sí", "s", "1", "true", "yes", "publica", "pública"):
        return True
    if text in ("no", "n", "0", "false", "privada"):
        return False
    raise ValueError(f"valor de columna 'publica' no reconocido: {value!r}")


def publica_str(is_public) -> str:
    return "si" if is_public else "no"


# ── Usuario actual (contexto Flask/Dash) ──────────────────────────────────────

def current_viewer() -> tuple[int | None, bool]:
    """(user_id, is_admin) del usuario actual.

    is_admin se toma de current_user.is_admin tal cual — incluye al
    GuestUser anónimo cuando el acceso público está habilitado (por diseño
    de la app ese guest opera como admin en TODAS las pantallas admin; ver
    app/auth/manager.py). Ese guest no tiene id → user_id None: puede ver
    y editar todo vía is_admin, y lo que cree queda sin dueño (editable
    solo por admins), pero nunca es "dueño" de nada."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return None, False
    uid = current_user.get_id()
    user_id = int(uid) if uid is not None else None
    return user_id, bool(getattr(current_user, "is_admin", False))


def visible_filter(model, user_id, is_admin):
    """Criterio SQLAlchemy de visibilidad para model (SignalDefinition o
    Strategy). Admin ve todo (devuelve True literal)."""
    import sqlalchemy as sa
    if is_admin:
        return sa.true()
    if user_id is None:
        return model.is_public.is_(True)
    return sa.or_(model.is_public.is_(True), model.owner_id == user_id)
