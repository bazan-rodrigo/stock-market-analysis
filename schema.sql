-- ============================================================
--  Database: stock-market-analysis
--  Schema for Stock Market Analysis System
-- ============================================================

CREATE DATABASE IF NOT EXISTS `sma`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `sma`;

-- ============================================================
-- USERS
-- ============================================================
CREATE TABLE users (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(150) NOT NULL UNIQUE,
  email VARCHAR(255),
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','analyst') NOT NULL DEFAULT 'analyst',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Usuario administrador inicial
-- Ese password_hash corresponde a la contraseña:
-- usuario: admin
-- password: admin123
INSERT INTO users (username, email, password_hash, role, is_active)
VALUES (
  'admin',
  'admin@example.com',
  'scrypt:32768:8:1$9u8A6FGcF3bTO65G$36670e697bc69e0e8fb1bbd3c2cdaf1d3b8e5149bd3d3c59ba1be69fcc48af267a8d19913ea96eff3720d8a9a389dc033d0de21f6f4595f3a10e50b5a3831877',
  'admin',
  1
);

-- ============================================================
-- PRICE SOURCES
-- ============================================================
CREATE TABLE price_sources (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  code VARCHAR(50) NOT NULL UNIQUE,
  api_type VARCHAR(50),
  base_url VARCHAR(255),
  notes TEXT,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_source_active (is_active),
  INDEX idx_source_code_active (code, is_active)
);

-- Después de crear tabla price_sources
INSERT INTO price_sources (code, name, source_type, base_url, is_active)
VALUES ('YAHOO', 'Yahoo Finance', 'api', 'https://query1.finance.yahoo.com', 1);

-- ============================================================
-- ASSETS
-- ============================================================
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
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (source_id) REFERENCES price_sources(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  INDEX idx_asset_source (source_id, source_symbol)
);

-- ============================================================
-- HISTORICAL PRICES
-- ============================================================
CREATE TABLE historical_prices (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  asset_id BIGINT NOT NULL,
  source_id BIGINT NOT NULL,
  date DATE NOT NULL,
  open DECIMAL(18,6),
  high DECIMAL(18,6),
  low DECIMAL(18,6),
  close DECIMAL(18,6),
  adj_close DECIMAL(18,6), 
  volume BIGINT,
  recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
  FOREIGN KEY (asset_id) REFERENCES assets(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  FOREIGN KEY (source_id) REFERENCES price_sources(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  UNIQUE KEY uq_asset_date (asset_id, date),
  INDEX idx_hp_asset_date (asset_id, date)
);


-- ============================================================
-- FAILED UPDATES
-- ============================================================
CREATE TABLE failed_updates (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  asset_id BIGINT NULL,
  source_id BIGINT NULL,
  run_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  run_type ENUM('scheduled', 'manual') NOT NULL DEFAULT 'scheduled',
  attempted_from DATE,
  attempted_to DATE,
  error_message TEXT,
  attempt_count INT DEFAULT 1,
  resolved TINYINT(1) DEFAULT 0, 
  resolved_at DATETIME NULL, 
  FOREIGN KEY (asset_id) REFERENCES assets(id)
    ON DELETE SET NULL
    ON UPDATE CASCADE,
  FOREIGN KEY (source_id) REFERENCES price_sources(id)
    ON DELETE SET NULL
    ON UPDATE CASCADE,
  INDEX idx_fu_source (source_id),
  INDEX idx_fu_run_timestamp (run_timestamp),
  INDEX idx_fu_resolved (resolved)
);

-- ============================================
-- TABLA: update_runs
-- ============================================
CREATE TABLE update_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  start_time DATETIME NOT NULL,
  end_time DATETIME,
  total_assets INT NOT NULL,
  updated_assets INT NOT NULL,
  run_type ENUM('manual','scheduled') NOT NULL DEFAULT 'manual',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
