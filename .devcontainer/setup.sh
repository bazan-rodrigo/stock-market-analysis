#!/bin/bash
set -e

# Asegurar que estamos en la raíz del proyecto
cd "$(dirname "$0")/.."

# ── Motor de base de datos: una elección de INSTALACIÓN ───────────────────
# El motor NO es una propiedad del entorno: se elige acá, una vez, y de él
# salen el servicio que se instala, el driver de Python y la URL con la que
# arranca la app. La elección se PERSISTE en conf.properties (gitignoreado,
# es la config de esta instalación) para que valga en cualquier shell y en
# cualquier proceso, no solo en el que corrió este script.
#
#   DB_ENGINE=postgres  → PostgreSQL (default; es lo que corre en producción)
#   DB_ENGINE=mysql     → MariaDB/MySQL
#
# NO existe un modo que instale los dos: montar un motor que no se va a usar
# es puro costo. Si alguna vez hay que compararlos, se levanta el segundo a
# mano — es un procedimiento de laboratorio, no una forma de instalar.
DB_ENGINE="$(echo "${DB_ENGINE:-postgres}" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
case "$DB_ENGINE" in
    postgres|postgresql|pg) DB_ENGINE="postgres" ;;
    mysql|mariadb)          DB_ENGINE="mysql" ;;
    *) echo "ERROR: DB_ENGINE='$DB_ENGINE' inválido (postgres | mysql)"; exit 1 ;;
esac
DB_NAME="${DB_NAME:-stock_analysis}"

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

    # mysqlclient es una extensión en C: necesita compilarse. psycopg trae
    # wheels, así que este bloque es exclusivo del camino MySQL.
    echo "=== Instalando dependencias del sistema para mysqlclient ==="
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        python3-dev default-libmysqlclient-dev build-essential pkg-config
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
    postgres) install_postgres ;;
    mysql)    install_mysql ;;
esac

# ── Persistir la elección ──────────────────────────────────────────────────
# conf.properties es la config de ESTA instalación (gitignoreado). Dejar el
# motor escrito ahí es lo que hace que la app derive sola el driver, el
# puerto y el usuario, sin depender de que alguien exporte variables.
echo "=== Registrando el motor elegido en conf.properties ==="
[ -f conf.properties ] || cp conf.properties.example conf.properties
if grep -q '^[[:space:]]*db_engine[[:space:]]*=' conf.properties; then
    sed -i "s/^[[:space:]]*db_engine[[:space:]]*=.*/db_engine = ${DB_ENGINE}/" conf.properties
else
    sed -i "/^\[settings\]/a db_engine = ${DB_ENGINE}" conf.properties
fi
echo "conf.properties: db_engine = ${DB_ENGINE}"

echo "=== Instalando dependencias Python ==="
pip install --upgrade pip -q
# El driver vive en un requirements aparte POR MOTOR: instalar el que no se
# usa es compilar una extensión en C para nada (ver requirements.txt).
pip install -r requirements.txt -r "requirements-${DB_ENGINE}.txt" -q
# Deps de dev (pytest, hypothesis): la pantalla /admin/verify corre la suite
# como subproceso con el mismo Python de la app, así que las necesita acá.
pip install -r requirements-dev.txt -q

echo "=== Inicializando base de datos (esquema + datos semilla) ==="
python scripts/init_db.py

echo ""
echo "======================================"
echo "  Codespace listo (motor: $DB_ENGINE)."
echo "  Ejecutar la app: python run.py"
echo "  URL: http://localhost:8050"
echo "  Usuario: admin / admin123"
echo "======================================"
