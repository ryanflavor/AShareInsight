-- AShareInsight Database Schema Initialization Script
-- This script creates the core database schema with pgvector extension support

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- For UUID generation
CREATE EXTENSION IF NOT EXISTS vector;       -- For vector similarity search

-- Drop existing tables if they exist (for clean re-initialization)
DROP TABLE IF EXISTS business_concepts_master CASCADE;
DROP TABLE IF EXISTS source_documents CASCADE;
DROP TABLE IF EXISTS companies CASCADE;

-- Create companies table (公司主表)
CREATE TABLE companies (
    company_code VARCHAR(10) PRIMARY KEY,      -- 公司股票代码作为唯一主键
    company_name_full VARCHAR(255) UNIQUE NOT NULL,  -- 公司完整官方名称
    company_name_short VARCHAR(100),           -- 公司简称
    exchange VARCHAR(50),                      -- 上市交易所
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),   -- 记录创建时间
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()    -- 记录最后更新时间
);

-- Create index on company_name_short for faster queries
CREATE INDEX idx_companies_name_short ON companies(company_name_short);

-- Create source_documents table (原始文档提取归档表)
CREATE TABLE source_documents (
    doc_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),  -- 文档提取记录唯一ID
    company_code VARCHAR(10) NOT NULL,         -- 关联到companies表
    doc_type VARCHAR(50) NOT NULL CHECK (doc_type IN ('annual_report', 'research_report')),  -- 文档类型
    doc_date DATE NOT NULL,                    -- 文档发布日期
    report_title TEXT NOT NULL,                -- 研报或年报标题
    raw_llm_output JSONB NOT NULL,             -- 存储从LLM返回的完整JSON
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),   -- 记录归档时间
    
    -- Foreign key constraint
    CONSTRAINT fk_source_documents_company 
        FOREIGN KEY (company_code) 
        REFERENCES companies(company_code) 
        ON DELETE CASCADE
);

-- Create indexes for source_documents
CREATE INDEX idx_source_documents_company_code ON source_documents(company_code);
CREATE INDEX idx_source_documents_doc_type ON source_documents(doc_type);
CREATE INDEX idx_source_documents_doc_date ON source_documents(doc_date DESC);
CREATE INDEX idx_source_documents_raw_llm_output ON source_documents USING GIN (raw_llm_output);  -- For JSONB queries

-- Create business_concepts_master table (业务概念主数据表)
CREATE TABLE business_concepts_master (
    concept_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),  -- 业务概念唯一ID
    company_code VARCHAR(10) NOT NULL,         -- 关联到companies表
    concept_name VARCHAR(255) NOT NULL,        -- 业务概念通用名称
    embedding VECTOR(2560) NOT NULL,           -- 由Qwen Embedding模型生成的向量
    concept_details JSONB,                     -- 存储概念所有其他详细信息
    last_updated_from_doc_id UUID NOT NULL,    -- 指向source_documents表追溯最新信息来源
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),   -- 该概念最后更新时间
    
    -- Foreign key constraints
    CONSTRAINT fk_business_concepts_company 
        FOREIGN KEY (company_code) 
        REFERENCES companies(company_code) 
        ON DELETE CASCADE,
    CONSTRAINT fk_business_concepts_document 
        FOREIGN KEY (last_updated_from_doc_id) 
        REFERENCES source_documents(doc_id) 
        ON DELETE RESTRICT  -- Prevent deletion of documents referenced by concepts
);

-- Create indexes for business_concepts_master
CREATE INDEX idx_business_concepts_company_code ON business_concepts_master(company_code);
CREATE INDEX idx_business_concepts_name ON business_concepts_master(concept_name);
CREATE INDEX idx_business_concepts_details ON business_concepts_master USING GIN (concept_details);  -- For JSONB queries

-- Note: HNSW index not created due to pgvector's 2000 dimension limit
-- The Qwen embedding model produces 2560-dimensional vectors
-- We'll use exact nearest neighbor search without index for now
-- Future optimization: implement dimensionality reduction or partitioning strategy

-- Create update trigger for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply update trigger to companies table
CREATE TRIGGER update_companies_updated_at 
    BEFORE UPDATE ON companies 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Apply update trigger to business_concepts_master table
CREATE TRIGGER update_business_concepts_updated_at 
    BEFORE UPDATE ON business_concepts_master 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Verify installation
SELECT 
    'PostgreSQL Version' as info_type, 
    version() as info_value
UNION ALL
SELECT 
    'pgvector Extension', 
    extname || ' ' || extversion 
FROM pg_extension 
WHERE extname = 'vector'
UNION ALL
SELECT 
    'UUID Extension', 
    extname || ' ' || extversion 
FROM pg_extension 
WHERE extname = 'uuid-ossp';

-- Show created tables
SELECT 
    tablename,
    schemaname
FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename IN ('companies', 'source_documents', 'business_concepts_master')
ORDER BY tablename;