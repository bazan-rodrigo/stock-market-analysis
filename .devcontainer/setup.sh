#!/bin/bash
set -e

# Asegurar que estamos en la raíz del proyecto
cd "$(dirname "$0")/.."

# ── Motor de base de datos ────────────────────────────────────────────────
# DB_ENGINE: mysql (default) | postgres | both
#   mysql    → MariaDB/MySQL, igual que siempre (la app usa los DB_* env).
#   postgres → PostgreSQL (PGDG); exporta DATABASE_URL en ~/.bashrc.
#   both     → los dos lado a lado (para la paridad del soporte dual);
#              la app corre contra MySQL salvo que se exporte DATABASE_URL.
# Ver docs/notes/design_postgresql_dual.md.
DB_ENGINE="${DB_ENGINE:-mysql}"
DB_NAME="${DB_NAME:-stock_analysis}"
PG_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/${DB_NAME}"

install_mysql() {
    echo "=== Instalando MariaDB / MySQL Server ==="
    sudo apt-get update -qq || true
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mariadb-server || \
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mysql-server

    echo "=== Iniciando base de datos ==="
    if sudo service mariadb start 2>/dev/null; then
        DB_SERVICE="mariadb"
    elif sudo service mysql start 2>/dev/null; then
        DB_SERVICE="mysql"
    else
        echo "ERROR: no se pudo iniciar mariadb ni mysql"
        exit 1
    fi
    echo "Servicio '$DB_SERVICE' iniciado."

    echo "=== Esperando que la BD esté lista ==="
    for i in {1..30}; do
        if sudo mysqladmin ping --silent 2>/dev/null; then
            echo "Base de datos lista."
            break
        fi
        echo "Intento $i/30 — esperando..."
        sleep 2
    done

    echo "=== Configurando usuario root sin password ==="
    sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY ''; FLUSH PRIVILEGES;" 2>/dev/null || \
    sudo mysql -e "UPDATE mysql.user SET authentication_string='' WHERE User='root'; FLUSH PRIVILEGES;" 2>/dev/null || true

    echo "=== Creando base de datos '$DB_NAME' ==="
    mysql -u root -h 127.0.0.1 -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
}

install_postgres() {
    echo "=== Instalando PostgreSQL (repo PGDG) ==="
    # bullseye trae PostgreSQL 13 (EOL nov-2026): usar el repo oficial
    sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | \
        sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
    sudo apt-get update -qq || true
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-16

    echo "=== Iniciando PostgreSQL ==="
    sudo service postgresql start

    echo "=== Esperando que PostgreSQL esté listo ==="
    for i in {1..30}; do
        if sudo -u postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL listo."
            break
        fi
        echo "Intento $i/30 — esperando..."
        sleep 2
    done

    echo "=== Configurando usuario postgres y base '$DB_NAME' ==="
    sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
        sudo -u postgres createdb "${DB_NAME}"
}

case "$DB_ENGINE" in
    mysql)    install_mysql ;;
    postgres) install_postgres ;;
    both)     install_mysql; install_postgres ;;
    *) echo "ERROR: DB_ENGINE='$DB_ENGINE' inválido (mysql|postgres|both)"; exit 1 ;;
esac

echo "=== Instalando dependencias del sistema para mysqlclient ==="
# Siempre: requirements.txt incluye mysqlclient (compila contra estas libs)
# aunque el motor elegido sea postgres — psycopg viene con wheels.
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3-dev default-libmysqlclient-dev build-essential pkg-config

echo "=== Instalando dependencias Python ==="
pip install --upgrade pip -q
pip install -r requirements.txt -q
# Deps de dev (pytest, hypothesis): la pantalla /admin/verify corre la suite
# como subproceso con el mismo Python de la app, así que las necesita acá.
pip install -r requirements-dev.txt -q

echo "=== Inicializando base de datos (esquema + datos semilla) ==="
if [ "$DB_ENGINE" = "postgres" ]; then
    # Motor único PG: la app también debe apuntar ahí en shells nuevas
    DATABASE_URL="$PG_URL" python scripts/init_db.py
    if ! grep -q "DATABASE_URL=" ~/.bashrc 2>/dev/null; then
        echo "export DATABASE_URL=\"$PG_URL\"" >> ~/.bashrc
        echo "DATABASE_URL exportada en ~/.bashrc (PostgreSQL)."
    fi
else
    python scripts/init_db.py                       # MySQL (DB_* del entorno)
    if [ "$DB_ENGINE" = "both" ]; then
        DATABASE_URL="$PG_URL" python scripts/init_db.py   # y PostgreSQL
    fi
fi

echo ""
echo "======================================"
echo "  Codespace listo (DB_ENGINE=$DB_ENGINE)."
echo "  Ejecutar la app: python run.py"
if [ "$DB_ENGINE" = "both" ]; then
    echo "  (contra PostgreSQL: DATABASE_URL=\"$PG_URL\" python run.py)"
fi
echo "  URL: http://localhost:8050"
echo "  Usuario: admin / admin123"
echo "======================================"
