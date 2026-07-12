"""
Visibilidad y permisos de señales/estrategias (app/services/visibility.py).

Modelo: owner_id controla la edición (solo dueño o admin); is_public solo
la visibilidad. Regla de referencias: pública solo referencia públicas;
privada, públicas + del mismo dueño.
"""
import pytest

from app.services.visibility import (
    can_edit, can_reference, can_view, parse_publica, publica_str,
)

ADMIN_ID = 1
ANA_ID   = 2
BETO_ID  = 3


# ── can_view ──────────────────────────────────────────────────────────────────

class TestCanView:
    def test_publica_la_ven_todos(self):
        assert can_view(ANA_ID, True, BETO_ID, False)
        assert can_view(None,   True, BETO_ID, False)
        assert can_view(ANA_ID, True, None,    False)   # invitado sin usuario

    def test_privada_la_ve_su_dueno(self):
        assert can_view(ANA_ID, False, ANA_ID, False)

    def test_privada_no_la_ve_otro_usuario(self):
        assert not can_view(ANA_ID, False, BETO_ID, False)

    def test_privada_no_la_ve_el_invitado(self):
        assert not can_view(ANA_ID, False, None, False)

    def test_admin_ve_todo(self):
        assert can_view(ANA_ID, False, ADMIN_ID, True)
        assert can_view(None,   False, ADMIN_ID, True)

    def test_privada_sin_dueno_solo_admin(self):
        # owner_id NULL con is_public=False: caso raro pero posible
        assert not can_view(None, False, ANA_ID, False)
        assert can_view(None, False, ADMIN_ID, True)


# ── can_edit ──────────────────────────────────────────────────────────────────

class TestCanEdit:
    def test_dueno_edita_la_suya_aunque_sea_publica(self):
        # "lo público es solo para la visibilidad": publicar no quita
        # el permiso de edición del dueño
        assert can_edit(ANA_ID, ANA_ID, False)

    def test_otro_usuario_no_edita(self):
        assert not can_edit(ANA_ID, BETO_ID, False)

    def test_admin_edita_todo(self):
        assert can_edit(ANA_ID, ADMIN_ID, True)
        assert can_edit(None,   ADMIN_ID, True)

    def test_sin_dueno_solo_admin(self):
        # owner_id NULL (packs importados pre-0065): edita solo el admin
        assert not can_edit(None, ANA_ID, False)

    def test_invitado_no_edita_nada(self):
        assert not can_edit(ANA_ID, None, False)
        assert not can_edit(None,   None, False)


# ── can_reference (composites, componentes, operandos del filtro) ─────────────

class TestCanReference:
    def test_publica_referencia_publica(self):
        assert can_reference(ANA_ID, True, BETO_ID, True)
        assert can_reference(ANA_ID, True, None,    True)

    def test_publica_no_referencia_privada_ni_siquiera_propia(self):
        # si se despublicara la dependencia quedaría rota para otros:
        # se exige publicar la dependencia primero
        assert not can_reference(ANA_ID, True, ANA_ID, False)
        assert not can_reference(ANA_ID, True, BETO_ID, False)

    def test_privada_referencia_publicas_y_propias(self):
        assert can_reference(ANA_ID, False, BETO_ID, True)   # pública ajena
        assert can_reference(ANA_ID, False, ANA_ID,  False)  # privada propia

    def test_privada_no_referencia_privada_ajena(self):
        assert not can_reference(ANA_ID, False, BETO_ID, False)
        assert not can_reference(ANA_ID, False, None,    False)

    def test_sin_dueno_solo_referencia_publicas(self):
        assert can_reference(None, False, BETO_ID, True)
        assert not can_reference(None, False, None, False)


# ── Columna `publica` de los xlsx ─────────────────────────────────────────────

class TestParsePublica:
    @pytest.mark.parametrize("val", [None, "", "si", "sí", "SI", "Sí", "s",
                                     "1", 1, "true", "yes", True,
                                     "publica", "pública"])
    def test_valores_publicos(self, val):
        assert parse_publica(val) is True

    @pytest.mark.parametrize("val", ["no", "NO", "n", "0", 0, "false",
                                     "privada", False])
    def test_valores_privados(self, val):
        assert parse_publica(val) is False

    def test_ausente_es_publica_por_compatibilidad(self):
        # packs anteriores a la columna: sin `publica` → pública
        assert parse_publica(None) is True

    def test_valor_no_reconocido_es_error(self):
        with pytest.raises(ValueError):
            parse_publica("quizas")

    def test_round_trip_con_export(self):
        assert parse_publica(publica_str(True)) is True
        assert parse_publica(publica_str(False)) is False
