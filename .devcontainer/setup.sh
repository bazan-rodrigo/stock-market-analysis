#!/bin/bash
set -e

echo "=== Instalando dependencias Python ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Esperando que MySQL esté listo ==="
for i in {1..30}; do
    if mysqladmin ping -h 127.0.0.1 -u root --silent 2>/dev/null; then
        echo "MySQL listo."
        break
    fi
    echo "Intento $i/30 — esperando MySQL..."
    sleep 2
done

echo "=== Creando base de datos '$DB_NAME' si no existe ==="
mysql -h 127.0.0.1 -u root -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo "=== Inicializando base de datos (migraciones + datos semilla) ==="
python scripts/init_db.py

echo ""
echo "======================================"
echo "  Codespace listo."
echo "  Ejecutar la app: python run.py"
echo "  URL: http://localhost:8050"
echo "  Usuario: admin / admin123"
echo "======================================"
