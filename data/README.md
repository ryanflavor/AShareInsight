# Data Directory Structure

This directory is designed to store 5000+ company annual reports and research analysis documents for the AShareInsight project.

## Directory Structure

```
data/
├── annual_reports/          # 年度报告原文
│   ├── 2020/               # 按年份组织
│   ├── 2021/
│   ├── 2022/
│   ├── 2023/
│   └── 2024/
├── research_reports/        # 研究报告原文
│   ├── 2023/
│   └── 2024/
├── extracted/              # LLM提取后的结构化数据
│   ├── annual_reports/     # 年报提取结果
│   └── research_reports/   # 研报提取结果
├── embeddings/             # 向量化数据（Story 1.3）
│   ├── annual_reports/
│   └── research_reports/
├── metadata/               # 元数据和索引文件
│   ├── company_index.json  # 公司索引
│   ├── document_index.json # 文档索引
│   └── processing_log.json # 处理日志
└── temp/                   # 临时文件和处理中的数据
```

## File Naming Convention

### Annual Reports
Format: `{company_code}_{company_name}_{year}_annual_report.{ext}`
Example: `300257_开山股份_2024_annual_report.md`

### Research Reports
Format: `{company_code}_{company_name}_{date}_{report_title}.{ext}`
Example: `688488_艾迪药业_20240115_公司信息更新报告.txt`

### Extracted Data
Format: `{original_filename}_extracted.json`
Example: `300257_开山股份_2024_annual_report_extracted.json`

## Storage Guidelines

1. **Original Documents**: Store in `annual_reports/` or `research_reports/` by year
2. **Extracted JSON**: Store in `extracted/` maintaining the same subdirectory structure
3. **Embeddings**: Will be stored in `embeddings/` (for Story 1.3)
4. **Metadata**: 
   - `company_index.json`: Maps company codes to company information
   - `document_index.json`: Maps document IDs to file paths and metadata
   - `processing_log.json`: Tracks processing status and errors

## Batch Processing

Use the batch processing script (see `scripts/batch_extract_all.py`) to:
- Automatically scan all documents in the data directory
- Extract structured data using LLM
- Track processing progress and handle failures
- Generate embeddings for Story 1.3

## Capacity Planning

- Expected: 5000+ documents
- Average document size: 50-100 KB (text)
- Average extraction size: 10-20 KB (JSON)
- Total estimated storage: ~1 GB for documents + ~100 MB for extractions