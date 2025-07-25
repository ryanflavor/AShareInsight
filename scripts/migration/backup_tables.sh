#!/bin/bash
# 备份关键表的脚本

BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "📦 开始备份数据库表..."

# 备份source_documents表
echo "备份 source_documents 表..."
pg_dump -U ashareinsight -h localhost ashareinsight_db -t source_documents > "$BACKUP_DIR/source_documents.sql"

# 备份business_concepts_master表
echo "备份 business_concepts_master 表..."
pg_dump -U ashareinsight -h localhost ashareinsight_db -t business_concepts_master > "$BACKUP_DIR/business_concepts_master.sql"

# 备份companies表
echo "备份 companies 表..."
pg_dump -U ashareinsight -h localhost ashareinsight_db -t companies > "$BACKUP_DIR/companies.sql"

echo "✅ 备份完成！备份位置: $BACKUP_DIR"
echo "文件列表:"
ls -lh "$BACKUP_DIR"