-- ============================================================
--  Database: stock-market-analysis
--  Schema for Stock Market Analysis System
-- ============================================================

CREATE DATABASE IF NOT EXISTS `stock-market-analysis`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `stock-market-analysis`;

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
  UNIQUE KEY uq_asset_trade_date (asset_id, trade_date),
  INDEX idx_hp_asset_date (asset_id, trade_date)
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
