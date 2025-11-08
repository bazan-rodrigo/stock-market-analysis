-- ============================================================
--  Database: stock-market-analysis
--  Optimized schema for Stock Market Analysis System
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
  price_date DATE NOT NULL,
  open DECIMAL(18,6),
  high DECIMAL(18,6),
  low DECIMAL(18,6),
  close DECIMAL(18,6),
  volume BIGINT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (asset_id) REFERENCES assets(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  FOREIGN KEY (source_id) REFERENCES price_sources(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  UNIQUE KEY uq_asset_price_date (asset_id, price_date),
  INDEX idx_hp_asset_date (asset_id, price_date)
);

-- ============================================================
-- FAILED UPDATES
-- ============================================================
CREATE TABLE failed_updates (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  source_id BIGINT,
  asset_id BIGINT,
  error_message TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (source_id) REFERENCES price_sources(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  FOREIGN KEY (asset_id) REFERENCES assets(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
  INDEX idx_fu_source (source_id),
  INDEX idx_fu_created (created_at)
);
