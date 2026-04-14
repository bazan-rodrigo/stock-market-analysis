#!/bin/bash
set -e

echo "=== Instalando MySQL Server ==="
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mysql-server

echo "=== Iniciando MySQL ==="
sudo service mysql start

echo "=== Esperando que MySQL esté listo ==="
for i in {1..30}; do
    if sudo mysqladmin ping --silent 2>/dev/null; then
        echo "MySQL listo."
        break
    fi
    echo "Intento $i/30 — esperando MySQL..."
    sleep 2
done

echo "=== Configurando usuario root sin password ==="
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY ''; FLUSH PRIVILEGES;" 2>/dev/null || true

echo "=== Creando base de datos '$DB_NAME' ==="
mysql -u root -h 127.0.0.1 -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "=== Instalando dependencias Python ==="
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "=== Inicializando base de datos (migraciones + datos semilla) ==="
python scripts/init_db.py

echo ""
echo "======================================"
echo "  Codespace listo."
echo "  Ejecutar la app: python run.py"
echo "  URL: http://localhost:8050"
echo "  Usuario: admin / admin123"
echo "======================================"
