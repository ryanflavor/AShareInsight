-- Migrate existing VECTOR(2560) to HALFVEC(2560) for HNSW indexing
-- Requires pgvector 0.7.0+

BEGIN;

-- Verify pgvector supports halfvec
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'halfvec') THEN
        RAISE EXCEPTION 'halfvec not supported. Upgrade to pgvector 0.7.0+';
    END IF;
END $$;

-- Migrate if needed
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'business_concepts_master' 
        AND column_name = 'embedding' AND udt_name = 'vector'
    ) THEN
        -- Drop old index
        DROP INDEX IF EXISTS idx_business_concepts_embedding_hnsw;
        
        -- Convert column
        ALTER TABLE business_concepts_master 
        ALTER COLUMN embedding TYPE HALFVEC(2560) 
        USING embedding::HALFVEC(2560);
        
        -- Create HNSW index
        CREATE INDEX idx_business_concepts_embedding_hnsw 
        ON business_concepts_master 
        USING hnsw (embedding halfvec_l2_ops)
        WITH (m = 32, ef_construction = 128);
        
        RAISE NOTICE 'Migration completed ✓';
    ELSE
        RAISE NOTICE 'No migration needed';
    END IF;
END $$;

COMMIT;