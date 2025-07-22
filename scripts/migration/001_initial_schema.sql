-- AShareInsight Initial Database Schema
-- Version: 1.0
-- Description: Creates the initial database schema for AShareInsight with pgvector support

-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Create companies table
CREATE TABLE IF NOT EXISTS companies (
    company_code VARCHAR(10) PRIMARY KEY NOT NULL,
    company_name_full VARCHAR(255) UNIQUE NOT NULL,
    company_name_short VARCHAR(100),
    exchange VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on company_name_short for faster searches
CREATE INDEX idx_company_name_short ON companies(company_name_short);

-- Create trigger to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_companies_updated_at BEFORE UPDATE
    ON companies FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create source_documents table
CREATE TABLE IF NOT EXISTS source_documents (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_code VARCHAR(10) NOT NULL REFERENCES companies(company_code) ON DELETE CASCADE,
    doc_type VARCHAR(50) NOT NULL CHECK (doc_type IN ('annual_report', 'research_report', 'announcement', 'other')),
    doc_date DATE NOT NULL,
    report_title TEXT,
    file_path TEXT,
    file_hash VARCHAR(64),
    raw_llm_output JSONB NOT NULL,
    extraction_metadata JSONB,
    processing_status VARCHAR(20) DEFAULT 'completed' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create composite index for efficient company + date queries
CREATE INDEX idx_source_docs_company_date ON source_documents(company_code, doc_date DESC);

-- Create index on processing_status for monitoring
CREATE INDEX idx_source_docs_status ON source_documents(processing_status) WHERE processing_status != 'completed';

-- Create GIN index on JSONB fields for efficient querying
CREATE INDEX idx_source_docs_raw_output ON source_documents USING GIN (raw_llm_output);
CREATE INDEX idx_source_docs_metadata ON source_documents USING GIN (extraction_metadata);

-- Create business_concepts_master table
CREATE TABLE IF NOT EXISTS business_concepts_master (
    concept_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_code VARCHAR(10) NOT NULL REFERENCES companies(company_code) ON DELETE CASCADE,
    concept_name VARCHAR(255) NOT NULL,
    concept_category VARCHAR(50) NOT NULL CHECK (concept_category IN ('product', 'service', 'technology', 'business_model', 'market', 'strategy', 'other')),
    importance_score DECIMAL(3,2) NOT NULL CHECK (importance_score >= 0 AND importance_score <= 1),
    development_stage VARCHAR(50) CHECK (development_stage IN ('concept', 'development', 'pilot', 'commercialization', 'mature', 'declining')),
    embedding halfvec(${VECTOR_DIMENSION}) NOT NULL,
    concept_details JSONB NOT NULL,
    last_updated_from_doc_id UUID REFERENCES source_documents(doc_id) ON DELETE SET NULL,
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for business_concepts_master
CREATE INDEX idx_concepts_company ON business_concepts_master(company_code);
CREATE INDEX idx_concepts_importance ON business_concepts_master(importance_score DESC);
CREATE INDEX idx_concepts_category ON business_concepts_master(concept_category);
CREATE INDEX idx_concepts_active ON business_concepts_master(is_active) WHERE is_active = true;

-- Create HNSW index for high-speed vector similarity search
-- Using configurable distance metric for similarity calculation
CREATE INDEX idx_concepts_embedding ON business_concepts_master 
USING hnsw (embedding halfvec_${DISTANCE_METRIC}_ops)
WITH (m = ${HNSW_M}, ef_construction = ${HNSW_EF_CONSTRUCTION});

-- Create trigger for business_concepts_master updated_at
CREATE TRIGGER update_business_concepts_updated_at BEFORE UPDATE
    ON business_concepts_master FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create unique constraint to prevent duplicate active concepts
CREATE UNIQUE INDEX idx_unique_active_concept 
ON business_concepts_master(company_code, concept_name, concept_category) 
WHERE is_active = true;

-- Create GIN index on concept_details for efficient JSONB queries
CREATE INDEX idx_concepts_details ON business_concepts_master USING GIN (concept_details);

-- Create a view for easy access to the latest active concepts with their sources
CREATE OR REPLACE VIEW v_active_concepts AS
SELECT 
    bc.concept_id,
    bc.company_code,
    c.company_name_full,
    c.company_name_short,
    bc.concept_name,
    bc.concept_category,
    bc.importance_score,
    bc.development_stage,
    bc.concept_details,
    bc.version,
    bc.created_at,
    bc.updated_at,
    sd.doc_type as last_source_type,
    sd.doc_date as last_source_date,
    sd.report_title as last_source_title
FROM business_concepts_master bc
JOIN companies c ON bc.company_code = c.company_code
LEFT JOIN source_documents sd ON bc.last_updated_from_doc_id = sd.doc_id
WHERE bc.is_active = true;

-- Create a function to search similar concepts using vector similarity
CREATE OR REPLACE FUNCTION search_similar_concepts(
    query_embedding halfvec(${VECTOR_DIMENSION}),
    similarity_threshold float DEFAULT 0.7,
    limit_results int DEFAULT 10
)
RETURNS TABLE (
    concept_id UUID,
    company_code VARCHAR(10),
    concept_name VARCHAR(255),
    concept_category VARCHAR(50),
    importance_score DECIMAL(3,2),
    similarity_score float
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        bc.concept_id,
        bc.company_code,
        bc.concept_name,
        bc.concept_category,
        bc.importance_score,
        1 - (bc.embedding <=> query_embedding) as similarity_score
    FROM business_concepts_master bc
    WHERE bc.is_active = true
      AND 1 - (bc.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY bc.embedding <=> query_embedding
    LIMIT limit_results;
END;
$$ LANGUAGE plpgsql;

-- Add comments to tables and columns for documentation
COMMENT ON TABLE companies IS 'A股上市公司基本信息表';
COMMENT ON COLUMN companies.company_code IS '公司股票代码，如 000333';
COMMENT ON COLUMN companies.company_name_full IS '公司全称';
COMMENT ON COLUMN companies.company_name_short IS '公司简称';
COMMENT ON COLUMN companies.exchange IS '交易所：SSE（上交所）、SZSE（深交所）';

COMMENT ON TABLE source_documents IS '原始文档信息表，存储年报、研报等文档及LLM提取结果';
COMMENT ON COLUMN source_documents.raw_llm_output IS 'LLM原始输出的完整JSON';
COMMENT ON COLUMN source_documents.extraction_metadata IS '提取过程的元数据（模型版本、提示词版本、耗时等）';

COMMENT ON TABLE business_concepts_master IS '业务概念主表，存储企业的核心业务概念及其向量表示';
COMMENT ON COLUMN business_concepts_master.embedding IS '使用Qwen3-Embedding-4B生成的2560维向量';
COMMENT ON COLUMN business_concepts_master.concept_details IS '概念详细信息的JSON对象';

-- Create database version tracking table
CREATE TABLE IF NOT EXISTS schema_versions (
    version_id SERIAL PRIMARY KEY,
    version_number VARCHAR(20) NOT NULL UNIQUE,
    description TEXT,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert initial version
INSERT INTO schema_versions (version_number, description) 
VALUES ('1.0.0', 'Initial schema with companies, source_documents, and business_concepts_master tables');