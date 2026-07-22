"""Guardia del último administrador (reference_service).

Sin el modo invitado (eliminado jul-2026) no hay puerta de atrás: si el
sistema se queda sin ningún admin activo, nadie puede volver a administrar
desde la aplicación. La pantalla de Usuarios no validaba ese caso — se podía
desactivar, degradar o borrar al último admin sin aviso.

La regla: una operación se bloquea SOLO si el afectado es hoy un admin activo,
dejaría de serlo, y no queda ningún otro admin activo. Tocar analistas o
admins inactivos nunca se bloquea.
"""
import pytest

from app.database import engine, get_session
from app.models import User
from app.services import reference_service as svc
from app.services.reference_service import deja_sin_admins


# ── Lógica pura ──────────────────────────────────────────────────────────────

def test_bloquea_al_ultimo_admin_activo():
    assert deja_sin_admins(era_admin_activo=True, queda_admin_activo=False,
                           otros_admins_activos=0) is True


def test_no_bloquea_si_queda_otro_admin():
    assert deja_sin_admins(True, False, otros_admins_activos=1) is False


def test_no_bloquea_si_sigue_siendo_admin_activo():
    # Editarle el nombre o la contraseña al último admin no es problema
    assert deja_sin_admins(True, True, 0) is False


def test_no_bloquea_operaciones_sobre_no_admins():
    # Borrar/desactivar un analista nunca se bloquea, ni siquiera en una
    # instalación que ya está (mal) sin admins activos: esa situación no la
    # creó esta operación y bloquear no la arregla.
    assert deja_sin_admins(False, False, 0) is False
    assert deja_sin_admins(False, True, 0) is False   # promover, menos aún


# ── Servicio contra el stub sqlite ───────────────────────────────────────────

@pytest.fixture()
def usuarios_limpios():
    """Tablas creadas y tabla users vacía antes y después del test."""
    from app.database import Base
    Base.metadata.create_all(engine)
    s = get_session()
    s.query(User).delete()
    s.commit()
    yield s
    s.query(User).delete()
    s.commit()


def _crear(s, username, role="admin", active=True):
    u = User(username=username, role=role, active=active)
    u.set_password("x")
    s.add(u)
    s.commit()
    return u


def test_no_se_puede_desactivar_al_ultimo_admin(usuarios_limpios):
    s = usuarios_limpios
    admin = _crear(s, "unico_admin")
    with pytest.raises(ValueError, match="último administrador"):
        svc.update_user(admin.id, "unico_admin", "admin", active=False)
    s.refresh(admin)
    assert admin.active is True     # no se aplicó nada


def test_no_se_puede_degradar_al_ultimo_admin(usuarios_limpios):
    s = usuarios_limpios
    admin = _crear(s, "unico_admin")
    with pytest.raises(ValueError, match="último administrador"):
        svc.update_user(admin.id, "unico_admin", "analyst", active=True)
    s.refresh(admin)
    assert admin.role == "admin"


def test_no_se_puede_borrar_al_ultimo_admin(usuarios_limpios):
    s = usuarios_limpios
    admin = _crear(s, "unico_admin")
    analista = _crear(s, "ana", role="analyst")
    with pytest.raises(ValueError, match="último administrador"):
        svc.delete_user(admin.id)
    assert s.get(User, admin.id) is not None
    # El analista sí se puede borrar aunque no haya más admins que este
    svc.delete_user(analista.id)
    assert s.get(User, analista.id) is None


def test_con_otro_admin_activo_todo_se_permite(usuarios_limpios):
    s = usuarios_limpios
    a1 = _crear(s, "admin1")
    a2 = _crear(s, "admin2")
    svc.update_user(a1.id, "admin1", "analyst", active=True)   # degradar OK
    svc.delete_user(a1.id)                                     # borrar OK
    with pytest.raises(ValueError, match="último administrador"):
        svc.delete_user(a2.id)                                 # el último no


def test_un_admin_inactivo_no_cuenta_como_respaldo(usuarios_limpios):
    s = usuarios_limpios
    activo = _crear(s, "activo")
    _crear(s, "dormido", active=False)
    with pytest.raises(ValueError, match="último administrador"):
        svc.update_user(activo.id, "activo", "admin", active=False)


def test_editar_al_ultimo_admin_sin_quitarle_el_rol_funciona(usuarios_limpios):
    s = usuarios_limpios
    admin = _crear(s, "unico_admin")
    svc.update_user(admin.id, "renombrado", "admin", active=True,
                    password="nueva")
    s.refresh(admin)
    assert admin.username == "renombrado"
    assert admin.check_password("nueva")


def test_reactivar_o_promover_nunca_se_bloquea(usuarios_limpios):
    s = usuarios_limpios
    dormido = _crear(s, "dormido", active=False)
    svc.update_user(dormido.id, "dormido", "admin", active=True)
    s.refresh(dormido)
    assert dormido.active is True


# ── Unicidad del nombre sin distinguir mayúsculas ────────────────────────────
#
# El login resuelve con ci_equals (contrato heredado de la collation
# case-insensitive de MySQL), pero el UNIQUE de la columna SÍ distingue caso en
# PostgreSQL: sin esta validación, 'Admin' y 'admin' conviven y el login queda
# resolviendo una u otra según el plan de ejecución.

def test_no_se_puede_crear_un_usuario_que_solo_difiere_en_mayusculas(
        usuarios_limpios):
    s = usuarios_limpios
    _crear(s, "ana", role="analyst")
    with pytest.raises(ValueError, match="mayúsculas"):
        svc.create_user("ANA", "x", "analyst")
    with pytest.raises(ValueError, match="mayúsculas"):
        svc.create_user("  Ana  ", "x", "analyst")   # se compara ya recortado
    assert s.query(User).count() == 1


def test_no_se_puede_renombrar_pisando_a_otro_usuario(usuarios_limpios):
    s = usuarios_limpios
    _crear(s, "admin1")
    otro = _crear(s, "ana", role="analyst")
    with pytest.raises(ValueError, match="mayúsculas"):
        svc.update_user(otro.id, "ADMIN1", "analyst", active=True)
    s.refresh(otro)
    assert otro.username == "ana"


def test_renombrarse_a_si_mismo_cambiando_el_caso_esta_permitido(
        usuarios_limpios):
    """El usuario editado se excluye del chequeo: si no, nadie podría
    corregirle las mayúsculas a su propio nombre."""
    s = usuarios_limpios
    admin = _crear(s, "unico_admin")
    svc.update_user(admin.id, "Unico_Admin", "admin", active=True)
    s.refresh(admin)
    assert admin.username == "Unico_Admin"
