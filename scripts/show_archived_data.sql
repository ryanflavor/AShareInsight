-- 查看归档的文档总数
SELECT 
    doc_type,
    COUNT(*) as document_count,
    MIN(created_at) as first_created,
    MAX(created_at) as last_created
FROM source_documents
GROUP BY doc_type
ORDER BY doc_type;

-- 查看最近归档的10个文档
SELECT 
    doc_id,
    company_code,
    doc_type,
    report_title,
    created_at,
    LENGTH(raw_llm_output::text) as json_size_bytes
FROM source_documents
ORDER BY created_at DESC
LIMIT 10;

-- 查看特定公司的文档
SELECT 
    company_code,
    doc_type,
    report_title,
    doc_date,
    created_at
FROM source_documents
WHERE company_code IN ('300257', '300663', '002747')
ORDER BY company_code, doc_date;

-- 查看原始JSON数据示例（开山股份）
SELECT 
    company_code,
    report_title,
    jsonb_pretty(raw_llm_output) as raw_json
FROM source_documents
WHERE company_code = '300257'
LIMIT 1;