"""Quién está pidiendo, cuando no hay request de Flask.

Todas las pantallas resuelven el usuario con `visibility.current_viewer()`, que
lee `flask_login.current_user`. **Fuera de un request eso no existe**: la capa
de IA corre en otro proceso (el servidor MCP), sin sesión web. `AiCaller` es el
reemplazo explícito — y explícito es el punto: no hay ningún valor por defecto
del que una herramienta pueda deducir un rol.

Por qué importa acá más que en otro lado: el gate de visibilidad de esta
aplicación **vive en las pantallas, no en los servicios**. Hay más de cien
llamadas a `current_viewer()`/`get_visible_*` en callbacks y páginas, mientras
que servicios como `data_explorer_service.fetch()` devuelven lo que les pidan
sin filtrar nada — el gate era que la pantalla fuera admin-only. Una capa nueva
que llame a los servicios directo **no hereda ese gate: tiene que re-aplicarlo**.
Por eso el caller viaja como primer argumento de toda herramienta y por eso
`registry.call()` no sabe construir uno.
"""
from dataclasses import dataclass, field

# ── Scopes ───────────────────────────────────────────────────────────────────
# Un scope es lo que un token concede, no lo que el usuario puede. Los dos se
# exigen: el scope acota lo que la herramienta tiene permitido intentar, y el
# rol/propiedad del usuario decide qué datos devuelve. Un token de admin con
# scope solo de lectura no escribe; un token con scope de escritura de un
# analista no toca lo que su usuario no podría tocar desde la pantalla.
SCOPE_READ = "read"          # consultar datos y definiciones visibles
SCOPE_WRITE_PACKS = "write:packs"   # importar packs (fase 2)
SCOPE_RUN_JOBS = "run:jobs"         # disparar corridas largas (fase 2)

SCOPES = frozenset({SCOPE_READ, SCOPE_WRITE_PACKS, SCOPE_RUN_JOBS})


class ScopeDenegado(PermissionError):
    """El token no concede el scope que la herramienta exige."""


@dataclass(frozen=True)
class AiCaller:
    """Identidad de quien invoca una herramienta.

    `user_id`/`is_admin` son EXACTAMENTE lo que devolvería `current_viewer()`
    para ese usuario en la web: la capa de IA no puede ver más que la pantalla
    equivalente. `user_id=None` es anónimo, que no es dueño de nada.
    """

    user_id: int | None
    is_admin: bool = False
    scopes: frozenset = field(default_factory=lambda: frozenset({SCOPE_READ}))

    def __post_init__(self):
        desconocidos = set(self.scopes) - SCOPES
        if desconocidos:
            raise ValueError(f"scopes desconocidos: {sorted(desconocidos)}")

    def viewer(self) -> tuple[int | None, bool]:
        """(user_id, is_admin) — la misma tupla que `current_viewer()`, para
        pasarla tal cual a `get_visible_*` y a `visible_filter`."""
        return self.user_id, self.is_admin

    def exigir(self, scope: str) -> None:
        if scope not in self.scopes:
            raise ScopeDenegado(
                f"esta operación requiere el permiso '{scope}' y el token no "
                f"lo tiene (tiene: {', '.join(sorted(self.scopes)) or 'ninguno'})")
