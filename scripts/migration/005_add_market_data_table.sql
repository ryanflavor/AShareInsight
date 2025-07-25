-- Migration: Add market data tables and views
-- Date: 2025-07-24
-- Purpose: Store daily market snapshots for A-share companies

-- Daily snapshot table for efficient 5-day average calculation
CREATE TABLE IF NOT EXISTS market_data_daily (
    company_code VARCHAR(10),
    trading_date DATE,
    total_market_cap DECIMAL(20, 2),      -- Total market cap in CNY
    circulating_market_cap DECIMAL(20, 2), -- Circulating market cap in CNY
    turnover_amount DECIMAL(20, 2),        -- Turnover amount in CNY (volume in CNY)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (company_code, trading_date)
);

-- Add foreign key constraint after ensuring companies table exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'companies') THEN
        ALTER TABLE market_data_daily 
        ADD CONSTRAINT fk_market_data_company 
        FOREIGN KEY (company_code) 
        REFERENCES companies(company_code)
        ON DELETE CASCADE;
    END IF;
END $$;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_market_data_daily_date ON market_data_daily(trading_date);
CREATE INDEX IF NOT EXISTS idx_market_data_daily_cap ON market_data_daily(total_market_cap);
CREATE INDEX IF NOT EXISTS idx_market_data_daily_turnover ON market_data_daily(turnover_amount);
CREATE INDEX IF NOT EXISTS idx_market_data_daily_company_date ON market_data_daily(company_code, trading_date DESC);

-- View for current market data with 5-day average
CREATE OR REPLACE VIEW market_data_current AS
WITH latest_trading_date AS (
    SELECT MAX(trading_date) as max_date 
    FROM market_data_daily
),
recent_data AS (
    SELECT 
        m.company_code,
        m.trading_date,
        m.total_market_cap,
        m.circulating_market_cap,
        m.turnover_amount,
        ROW_NUMBER() OVER (PARTITION BY m.company_code ORDER BY m.trading_date DESC) as rn
    FROM market_data_daily m
    CROSS JOIN latest_trading_date ltd
    WHERE m.trading_date >= ltd.max_date - INTERVAL '7 days'
)
SELECT 
    r1.company_code,
    r1.total_market_cap as current_market_cap,
    r1.circulating_market_cap as current_circulating_cap,
    r1.turnover_amount as today_volume,
    COALESCE(
        AVG(r2.turnover_amount) FILTER (WHERE r2.rn BETWEEN 2 AND 6),
        r1.turnover_amount
    ) as avg_5day_volume,
    r1.trading_date as last_updated
FROM recent_data r1
LEFT JOIN recent_data r2 
    ON r1.company_code = r2.company_code
WHERE r1.rn = 1
GROUP BY r1.company_code, r1.total_market_cap, r1.circulating_market_cap, 
         r1.turnover_amount, r1.trading_date;

-- Add comment for documentation
COMMENT ON TABLE market_data_daily IS 'Daily market data snapshots for A-share companies';
COMMENT ON VIEW market_data_current IS 'Current market data with 5-day average volume calculations';