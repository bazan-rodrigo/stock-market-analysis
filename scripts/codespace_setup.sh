#!/bin/bash
# Setup y validacion del entorno en GitHub Codespaces
#
# DB_ENGINE: mysql (default) | postgres | both — ver
# docs/notes/design_postgresql_dual.md. La rama postgres asume el repo
# PGDG ya configurado por .devcontainer/setup.sh (o instala de apt).
set -e

PASS=0
FAIL=0

ok()   { echo "[OK]   $1"; PASS=$((PASS+1)); }
fail() { echo "[FAIL] $1"; FAIL=$((FAIL+1)); }
step() { echo ""; echo ">>> $1"; }

DB_ENGINE="${DB_ENGINE:-mysql}"
DB_NAME="${DB_NAME:-stock_analysis}"
PG_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/${DB_NAME}"

setup_mysql() {
    # ─── MySQL instalado ───────────────────────────────────────────────────
    step "Verificando MySQL..."
    if command -v mysql &>/dev/null; then
        ok "MySQL ya instalado: $(mysql --version)"
    else
        echo "    Instalando MySQL Server..."
        sudo apt-get update -qq 2>/dev/null || true
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq default-mysql-server
        ok "MySQL instalado"
    fi

    # ─── MySQL/MariaDB corriendo ──────────────────────────────────────────
    step "Iniciando servicio de base de datos..."
    if sudo service mysql start 2>/dev/null; then
        DB_SERVICE="mysql"
    elif sudo service mariadb start 2>/dev/null; then
        DB_SERVICE="mariadb"
    else
        fail "No se encontro servicio mysql ni mariadb"
        exit 1
    fi
    sleep 2
    if sudo mysqladmin ping --silent 2>/dev/null; then
        ok "Servicio '$DB_SERVICE' corriendo"
    else
        fail "El servicio no responde — revisar con: sudo service $DB_SERVICE status"
        exit 1
    fi

    # ─── Configurar root sin password ─────────────────────────────────────
    step "Configurando usuario root..."
    sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY ''; FLUSH PRIVILEGES;" 2>/dev/null || \
    sudo mysql -e "UPDATE mysql.user SET authentication_string='' WHERE User='root'; FLUSH PRIVILEGES;" 2>/dev/null || true
    if mysql -u root -h 127.0.0.1 -e "SELECT 1;" &>/dev/null; then
        ok "Conexion root sin password OK"
    else
        fail "No se pudo conectar como root sin password"
        exit 1
    fi

    # ─── Base de datos ────────────────────────────────────────────────────
    step "Creando base de datos..."
    mysql -u root -h 127.0.0.1 -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    if mysql -u root -h 127.0.0.1 -e "USE \`${DB_NAME}\`;" &>/dev/null; then
        ok "Base de datos '$DB_NAME' existe"
    else
        fail "Base de datos '$DB_NAME' no existe"
        exit 1
    fi
}

setup_postgres() {
    # ─── PostgreSQL instalado ─────────────────────────────────────────────
    step "Verificando PostgreSQL..."
    if command -v psql &>/dev/null; then
        ok "PostgreSQL ya instalado: $(psql --version)"
    else
        echo "    Instalando PostgreSQL..."
        sudo apt-get update -qq 2>/dev/null || true
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-16 2>/dev/null || \
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql
        ok "PostgreSQL instalado"
    fi

    # ─── PostgreSQL corriendo ─────────────────────────────────────────────
    step "Iniciando PostgreSQL..."
    sudo service postgresql start 2>/dev/null || true
    sleep 2
    if sudo -u postgres pg_isready -q 2>/dev/null; then
        ok "PostgreSQL corriendo"
    else
        fail "PostgreSQL no responde — revisar con: sudo service postgresql status"
        exit 1
    fi

    # ─── Usuario y base ───────────────────────────────────────────────────
    step "Configurando usuario postgres y base..."
    sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';" >/dev/null
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
        sudo -u postgres createdb "${DB_NAME}"
    if PGPASSWORD=postgres psql -U postgres -h 127.0.0.1 -d "${DB_NAME}" -c "SELECT 1;" &>/dev/null; then
        ok "Base de datos '$DB_NAME' accesible en PostgreSQL"
    else
        fail "No se pudo conectar a '$DB_NAME' en PostgreSQL"
        exit 1
    fi
}

check_mysql_schema() {
    step "Inicializando esquema (MySQL)..."
    python scripts/init_db.py
    TABLES=$(mysql -u root -h 127.0.0.1 -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${DB_NAME}';" 2>/dev/null)
    if [ "$TABLES" -gt 0 ]; then
        ok "Tablas creadas: $TABLES tablas en '$DB_NAME' (MySQL)"
    else
        fail "No se encontraron tablas en '$DB_NAME' (MySQL)"
        exit 1
    fi

    step "Verificando usuario admin (MySQL)..."
    ADMIN=$(mysql -u root -h 127.0.0.1 -N -e "SELECT username FROM \`${DB_NAME}\`.users WHERE username='admin';" 2>/dev/null)
    if [ "$ADMIN" = "admin" ]; then
        ok "Usuario admin existe"
    else
        fail "Usuario admin no encontrado"
        exit 1
    fi
}

check_postgres_schema() {
    step "Inicializando esquema (PostgreSQL)..."
    DATABASE_URL="$PG_URL" python scripts/init_db.py
    TABLES=$(PGPASSWORD=postgres psql -U postgres -h 127.0.0.1 -d "${DB_NAME}" -tAc \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null)
    if [ "$TABLES" -gt 0 ]; then
        ok "Tablas creadas: $TABLES tablas en '$DB_NAME' (PostgreSQL)"
    else
        fail "No se encontraron tablas en '$DB_NAME' (PostgreSQL)"
        exit 1
    fi

    step "Verificando usuario admin (PostgreSQL)..."
    ADMIN=$(PGPASSWORD=postgres psql -U postgres -h 127.0.0.1 -d "${DB_NAME}" -tAc \
        "SELECT username FROM users WHERE username='admin';" 2>/dev/null)
    if [ "$ADMIN" = "admin" ]; then
        ok "Usuario admin existe"
    else
        fail "Usuario admin no encontrado"
        exit 1
    fi
}

# ─── Motor(es) ─────────────────────────────────────────────────────────────
case "$DB_ENGINE" in
    mysql)    setup_mysql ;;
    postgres) setup_postgres ;;
    both)     setup_mysql; setup_postgres ;;
    *) echo "ERROR: DB_ENGINE='$DB_ENGINE' invalido (mysql|postgres|both)"; exit 1 ;;
esac

# ─── Dependencias Python ───────────────────────────────────────────────────
step "Verificando dependencias Python..."
if python -c "import dash, flask, sqlalchemy, alembic, yfinance, plotly, numpy, pandas, apscheduler" &>/dev/null; then
    ok "Dependencias Python ya instaladas"
else
    echo "    Instalando requirements..."
    pip install -r requirements.txt -q
    if python -c "import dash, flask, sqlalchemy, alembic, yfinance, plotly, numpy, pandas, apscheduler" &>/dev/null; then
        ok "Dependencias instaladas correctamente"
    else
        fail "Error al instalar dependencias"
        exit 1
    fi
fi

# ─── Esquema + admin por motor ─────────────────────────────────────────────
case "$DB_ENGINE" in
    mysql)    check_mysql_schema ;;
    postgres) check_postgres_schema ;;
    both)     check_mysql_schema; check_postgres_schema ;;
esac

# ─── Importacion de la app ─────────────────────────────────────────────────
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
echo "  Resultado: $PASS OK  |  $FAIL FAIL   (DB_ENGINE=$DB_ENGINE)"
echo "======================================"
if [ "$FAIL" -eq 0 ]; then
    echo ""
    echo "  Todo listo. Levantar la app con:"
    echo "    python run.py"
    if [ "$DB_ENGINE" != "mysql" ]; then
        echo "  Contra PostgreSQL:"
        echo "    DATABASE_URL=\"$PG_URL\" python run.py"
    fi
    echo ""
    echo "  Usuario: admin / admin123"
fi
