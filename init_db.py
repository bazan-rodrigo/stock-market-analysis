# -*- coding: utf-8 -*-
"""
init_db.py
----------------------------------
Inicializa la base de datos 'stock-market-analysis' ejecutando schema_optimized.sql
Usa SQLAlchemy con el mismo DB_URI definido en el entorno.
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# =====================================================
# CARGAR VARIABLES DE ENTORNO
# =====================================================
load_dotenv()
DB_URI = os.getenv("DB_URI", "mysql+mysqlconnector://root:@localhost/stock-market-analysis")
SCHEMA_FILE = "schema.sql"

# =====================================================
# FUNCIÓN PRINCIPAL
# =====================================================
def execute_schema():
    print("🚀 Iniciando proceso de creación de la base de datos...")
    if not os.path.exists(SCHEMA_FILE):
        raise FileNotFoundError(f"No se encontró el archivo {SCHEMA_FILE}")

    # Leer archivo SQL
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        sql_script = f.read()

    # Crear conexión inicial (sin especificar base) para crearla si no existe
    uri_without_db = DB_URI.rsplit("/", 1)[0]
    if "?" in uri_without_db:
        uri_without_db = uri_without_db.split("?")[0]
    engine_root = create_engine(uri_without_db, echo=False)

    try:
        with engine_root.connect() as conn:
            conn.execute(text("CREATE DATABASE IF NOT EXISTS `stock-market-analysis` "
                              "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
            print("🧱 Base de datos creada o ya existente.")
    except SQLAlchemyError as e:
        print("❌ Error creando la base de datos:", e)
        return

    # Conectar ahora a la base correcta
    engine = create_engine(DB_URI, echo=False)
    try:
        with engine.connect() as conn:
            for stmt in sql_script.split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(text(stmt))
            print("✅ Tablas creadas correctamente en 'stock-market-analysis'.")

    except SQLAlchemyError as e:
        print("❌ Error ejecutando el schema:", e)
    finally:
        engine.dispose()
        print("🔒 Conexión cerrada.")

# =====================================================
# PUNTO DE ENTRADA
# =====================================================
if __name__ == "__main__":
    try:
        execute_schema()
    except Exception as e:
        print("❗ Error general:", e)
