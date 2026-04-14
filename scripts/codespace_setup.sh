#!/bin/bash
# Setup y validacion del entorno en GitHub Codespaces
set -e

PASS=0
FAIL=0

ok()   { echo "[OK]   $1"; PASS=$((PASS+1)); }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL+1)); }
step() { echo ""; echo ">>> $1"; }

# ─── 1. MySQL instalado ────────────────────────────────────────────────────
step "Verificando MySQL..."
if command -v mysql &>/dev/null; then
    ok "MySQL ya instalado: $(mysql --version)"
else
    echo "    Instalando MySQL Server..."
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mysql-server
    ok "MySQL instalado"
fi

# ─── 2. MySQL corriendo ────────────────────────────────────────────────────
step "Iniciando servicio MySQL..."
sudo service mysql start 2>/dev/null || true
sleep 2
if sudo mysqladmin ping --silent 2>/dev/null; then
    ok "MySQL corriendo"
else
    fail "MySQL no responde — revisar con: sudo service mysql status"
    exit 1
fi

# ─── 3. Configurar root sin password ──────────────────────────────────────
step "Configurando usuario root..."
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY ''; FLUSH PRIVILEGES;" 2>/dev/null || true
if mysql -u root -h 127.0.0.1 -e "SELECT 1;" &>/dev/null; then
    ok "Conexion root sin password OK"
else
    fail "No se pudo conectar como root sin password"
    exit 1
fi

# ─── 4. Base de datos ─────────────────────────────────────────────────────
step "Creando base de datos..."
DB_NAME="${DB_NAME:-stock_analysis}"
mysql -u root -h 127.0.0.1 -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
if mysql -u root -h 127.0.0.1 -e "USE \`${DB_NAME}\`;" &>/dev/null; then
    ok "Base de datos '$DB_NAME' existe"
else
    fail "Base de datos '$DB_NAME' no existe"
    exit 1
fi

# ─── 5. Dependencias Python ───────────────────────────────────────────────
step "Verificando dependencias Python..."
if python -c "import dash, flask, sqlalchemy, alembic, yfinance" &>/dev/null; then
    ok "Dependencias Python ya instaladas"
else
    echo "    Instalando requirements..."
    pip install -r requirements.txt -q
    if python -c "import dash, flask, sqlalchemy, alembic, yfinance" &>/dev/null; then
        ok "Dependencias instaladas correctamente"
    else
        fail "Error al instalar dependencias"
        exit 1
    fi
fi

# ─── 6. Migraciones Alembic ───────────────────────────────────────────────
step "Aplicando migraciones Alembic..."
python scripts/init_db.py
TABLES=$(mysql -u root -h 127.0.0.1 -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${DB_NAME}';" 2>/dev/null)
if [ "$TABLES" -gt 0 ]; then
    ok "Tablas creadas: $TABLES tablas en '$DB_NAME'"
else
    fail "No se encontraron tablas en '$DB_NAME'"
    exit 1
fi

# ─── 7. Usuario admin ─────────────────────────────────────────────────────
step "Verificando usuario admin..."
ADMIN=$(mysql -u root -h 127.0.0.1 -N -e "SELECT username FROM \`${DB_NAME}\`.user WHERE username='admin';" 2>/dev/null)
if [ "$ADMIN" = "admin" ]; then
    ok "Usuario admin existe"
else
    fail "Usuario admin no encontrado"
    exit 1
fi

# ─── 8. Importacion de la app ─────────────────────────────────────────────
step "Verificando que la app importa sin errores..."
if python -c "from app import create_app; create_app()" &>/dev/null; then
    ok "App importa correctamente"
else
    fail "Error al importar la app"
    python -c "from app import create_app; create_app()"
    exit 1
fi

# ─── Resumen ──────────────────────────────────────────────────────────────
echo ""
echo "======================================"
echo "  Resultado: $PASS OK  |  $FAIL FAIL"
echo "======================================"
if [ "$FAIL" -eq 0 ]; then
    echo ""
    echo "  Todo listo. Levantar la app con:"
    echo "    python run.py"
    echo ""
    echo "  Usuario: admin / admin123"
fi
