-- schema.sql
-- Estructura completa de la base de datos MySQL para Stock Market Analysis
-- No usa acentos ni eñes

CREATE DATABASE IF NOT EXISTS stock_analysis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE stock_analysis;

-- --------------------------------------------------------
-- USERS
-- --------------------------------------------------------
CREATE TABLE users (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(150) NOT NULL UNIQUE,
  email VARCHAR(255),
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','analyst') NOT NULL DEFAULT 'analyst',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NULL DEFAULT NULL
);

-- --------------------------------------------------------
-- PRICE SOURCES
-- --------------------------------------------------------
CREATE TABLE price_sources (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  code VARCHAR(50) NOT NULL UNIQUE,
  api_type VARCHAR(50),
  base_url VARCHAR(255),
  notes TEXT,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- --------------------------------------------------------
-- ASSETS
-- --------------------------------------------------------
CREATE TABLE assets (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  symbol VARCHAR(128) NOT NULL UNIQUE,
  name VARCHAR(255),
  sector VARCHAR(128),
  industry VARCHAR(128),
  country VARCHAR(64),
  currency VARCHAR(16),
  source_id BIGINT NOT NULL,
  source_symbol VARCHAR(128) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NULL DEFAULT NULL,
  CONSTRAINT fk_asset_source FOREIGN KEY (source_id) REFERENCES price_sources(id)
);

-- --------------------------------------------------------
-- HISTORICAL PRICES
-- --------------------------------------------------------
CREATE TABLE historical_prices (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  asset_id BIGINT NOT NULL,
  source_id BIGINT NOT NULL,
  trade_date DATE NOT NULL,
  open DECIMAL(18,6),
  high DECIMAL(18,6),
  low DECIMAL(18,6),
  close DECIMAL(18,6),
  adj_close DECIMAL(18,6),
  volume BIGINT,
  recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_asset_date (asset_id, trade_date),
  CONSTRAINT fk_hist_asset FOREIGN KEY (asset_id) REFERENCES assets(id),
  CONSTRAINT fk_hist_source FOREIGN KEY (source_id) REFERENCES price_sources(id)
)
PARTITION BY RANGE (YEAR(trade_date)) (
  PARTITION p2020 VALUES LESS THAN (2021),
  PARTITION p2021 VALUES LESS THAN (2022),
  PARTITION p2022 VALUES LESS THAN (2023),
  PARTITION p2023 VALUES LESS THAN (2024),
  PARTITION p2024 VALUES LESS THAN (2025),
  PARTITION p2025 VALUES LESS THAN (2026),
  PARTITION pmax VALUES LESS THAN MAXVALUE
);

-- --------------------------------------------------------
-- FAILED UPDATES
-- --------------------------------------------------------
CREATE TABLE failed_updates (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  asset_id BIGINT NULL,
  source_id BIGINT NULL,
  run_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  run_type ENUM('scheduled','manual') NOT NULL DEFAULT 'scheduled',
  attempted_from DATE NULL,
  attempted_to DATE NULL,
  error_message TEXT,
  attempt_count INT NOT NULL DEFAULT 1,
  resolved TINYINT(1) NOT NULL DEFAULT 0,
  resolved_at DATETIME NULL,
  CONSTRAINT fk_fail_asset FOREIGN KEY (asset_id) REFERENCES assets(id),
  CONSTRAINT fk_fail_source FOREIGN KEY (source_id) REFERENCES price_sources(id)
);

-- --------------------------------------------------------
-- UPDATE RUNS
-- --------------------------------------------------------
CREATE TABLE update_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  run_type ENUM('scheduled','manual') NOT NULL DEFAULT 'scheduled',
  total_assets INT NOT NULL DEFAULT 0,
  success_count INT NOT NULL DEFAULT 0,
  failure_count INT NOT NULL DEFAULT 0,
  notes TEXT
);

-- --------------------------------------------------------
-- PRICE SOURCE DEFAULT
-- --------------------------------------------------------
INSERT INTO price_sources (name, code, api_type, base_url, is_active)
VALUES ('Yahoo Finance', 'YAHOO', 'yfinance', 'https://query1.finance.yahoo.com', 1)
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- --------------------------------------------------------
-- USUARIO ADMINISTRADOR POR DEFECTO
-- --------------------------------------------------------
-- Este usuario permite acceder por primera vez a la aplicacion.
-- Usuario: admin
-- Clave:   admin
-- El password se almacena con hash SHA256 (bcrypt no disponible en SQL plano).
-- Si se reimporta el schema, esta insercion se omitira si el usuario ya existe.

INSERT INTO users (username, email, password_hash, role, is_active, created_at)
VALUES (
    'admin',
    'admin@example.com',
    -- Hash de "admin" generado con werkzeug.security.generate_password_hash("admin")
    'scrypt:32768:8:1$ZgHdI14eKxlSGAmd$95825b7b33d0e2ce2fae8c7cbf79a2a02e81a70809ac7b12a28cb25a6ac83b5c5e3bca82c2039df8f2c66f2b1f244b9b3d04d0e32fa8d0a0048a02a179bba11f',
    'admin',
    1,
    NOW()
)
ON DUPLICATE KEY UPDATE username=username;


-- --------------------------------------------------------
-- CONFIRMAR TRANSACCION
-- --------------------------------------------------------
COMMIT;