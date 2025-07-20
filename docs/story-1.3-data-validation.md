# Story 1.3 数据驱动验证方案

## 概述

基于 `/data` 目录下的真实提取数据，我们设计了一个完整的数据驱动验证方案，无需重新运行 LLM 提取，直接使用已有的提取结果进行归档验证。

## 真实数据清单

### 年报数据 (9个文件)
- `300257_开山股份_2024_annual_report_extracted.json`
- `300663_科蓝软件_2024_annual_report_extracted.json`
- `创业黑马_2024年年度报告摘要_extracted.json`
- `双一科技_2024年年度报告摘要_extracted.json`
- `广和通_2024年年度报告摘要_extracted.json`
- `扬帆新材_2024年年度报告摘要_extracted.json`
- `澄天伟业_2024年年度报告摘要_extracted.json`
- `磁谷科技_2024年年度报告摘要_extracted.json`
- `联合光电_2024年年度报告摘要_extracted.json`

### 研报数据 (7个文件)
- `002747_埃斯顿_20240120_人形机器人新品发布_extracted.json`
- `688488_艾迪药业_20240115_公司信息更新报告_extracted.json`
- `奥士康-002913-联接世界、导通未来_extracted.json`
- `奥来德-688378-材料实现单季度扭亏，中标京东方8.6代线设备订单_extracted.json`
- `奥海科技-002993-端侧AI驱动充电龙头成长，新能源汽车_服务器业务贡献新增长极_extracted.json`
- `百润股份-002568-威士忌产品矩阵初成_extracted.json`
- `芭田股份-002170-小高寨磷矿迎来放量，助推业绩高增，二期扩能稳步推进_extracted.json`

## 验证脚本

### 1. 数据导入脚本 (`scripts/import_existing_data.py`)

该脚本将已有的提取结果直接作为"原始 LLM 输出"导入到 `source_documents` 表：

```bash
# 导入所有已提取的数据
python scripts/import_existing_data.py
```

**核心逻辑**：
- 读取 `data/extracted/` 目录下的所有 JSON 文件
- 将整个 JSON 文件内容作为 `raw_llm_output` 字段保存
- 从 JSON 结构中提取必要的元数据（company_code, doc_type, doc_date 等）
- 计算文件哈希以保证幂等性
- 使用 `ArchiveExtractionResultUseCase` 执行归档

### 2. 数据验证脚本 (`scripts/verify_archive_data.py`)

该脚本验证数据是否正确归档到数据库：

```bash
# 验证归档结果
python scripts/verify_archive_data.py
```

**验证内容**：
- 统计数据库中的文档总数
- 按文档类型分组统计
- 抽样显示文档内容
- 验证特定公司的归档情况
- 对比源文件数量和归档数量

## 验证步骤

### 步骤 1：初始化数据库

```bash
# 确保 PostgreSQL 运行中
docker-compose up -d postgres

# 运行数据库迁移
alembic upgrade head
```

### 步骤 2：导入现有数据

```bash
# 导入所有提取结果
python scripts/import_existing_data.py
```

预期输出：
```
found_files annual_reports=9 research_reports=7 total=16
import_success file=data/extracted/annual_reports/300257_开山股份_2024_annual_report_extracted.json
...
import_complete total=16 success=16 failed=0
```

### 步骤 3：验证归档结果

```bash
# 运行验证脚本
python scripts/verify_archive_data.py
```

预期输出：
```
total_documents_archived count=16
document_type_count type=annual_report count=9
document_type_count type=research_report count=7
company_documents_found company_code=300257 count=1 types=['annual_report']
verification_passed message="All extracted files have been archived"
```

### 步骤 4：数据库查询验证

```sql
-- 查看归档的文档
SELECT doc_id, company_code, doc_type, report_title, created_at
FROM source_documents
ORDER BY created_at DESC
LIMIT 10;

-- 验证原始数据完整性
SELECT 
    doc_id,
    company_code,
    jsonb_pretty(raw_llm_output) as raw_output
FROM source_documents
WHERE company_code = '300257';

-- 统计各类型文档数量
SELECT doc_type, COUNT(*) as count
FROM source_documents
GROUP BY doc_type;
```

## 关键设计决策

1. **将提取结果直接作为 LLM 输出**：Story 1.2 的提取结果 JSON 本身就是需要归档的"原始 LLM 输出"

2. **元数据映射**：
   - `extraction_data.company_code` → `company_code`
   - `document_type` → `doc_type`
   - 生成合理的 `report_title` 和 `doc_date`

3. **幂等性保证**：使用 JSON 内容的 SHA-256 哈希作为 `file_hash`，防止重复导入

4. **事务完整性**：每个文件导入都在独立事务中，失败不影响其他文件

## 预期结果

- 16 个文件全部成功导入
- 数据库中包含完整的原始 JSON 数据
- 元数据字段正确映射
- 支持按公司代码、文档类型查询
- 重复运行脚本不会产生重复记录

## 使用场景

1. **开发验证**：验证 Story 1.3 的归档功能是否正确实现
2. **集成测试**：作为集成测试的测试数据
3. **性能测试**：测试批量归档的性能
4. **回归测试**：确保后续修改不破坏归档功能