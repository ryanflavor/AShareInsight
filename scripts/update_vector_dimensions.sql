-- Script to update vector dimensions from 1024 to 2560 for Qwen embeddings
-- This script should be run after the initial schema is created

-- First, we need to drop the existing HNSW index
DROP INDEX IF EXISTS idx_business_concepts_embedding_hnsw;

-- Drop the existing embedding column
ALTER TABLE business_concepts_master DROP COLUMN IF EXISTS embedding;

-- Add new embedding column with 2560 dimensions
ALTER TABLE business_concepts_master 
ADD COLUMN embedding VECTOR(2560) NOT NULL DEFAULT ARRAY_FILL(0, ARRAY[2560])::vector;

-- Remove the default after adding the column
ALTER TABLE business_concepts_master 
ALTER COLUMN embedding DROP DEFAULT;

-- Recreate HNSW index with optimized parameters for 2560-dimensional vectors
-- Increase m and ef_construction for higher dimensions
CREATE INDEX idx_business_concepts_embedding_hnsw 
ON business_concepts_master 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 32, ef_construction = 128);

-- Verify the change
SELECT 
    column_name,
    data_type,
    udt_name,
    character_maximum_length
FROM information_schema.columns
WHERE table_name = 'business_concepts_master' 
AND column_name = 'embedding';