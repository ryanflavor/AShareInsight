#!/bin/bash
# 增量提取脚本：自动扫描新文件，提取数据并存入数据库
# 
# 使用方式:
#   ./scripts/run_incremental_extract.sh                    # 处理所有新文件
#   ./scripts/run_incremental_extract.sh --type annual      # 仅处理年报
#   ./scripts/run_incremental_extract.sh --type research    # 仅处理研报
#   ./scripts/run_incremental_extract.sh --force            # 强制重新处理所有文件

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查环境变量
check_environment() {
    if [ -z "$GEMINI_API_KEY" ]; then
        log_error "GEMINI_API_KEY environment variable is not set"
        echo "Please run: export GEMINI_API_KEY=<your-api-key>"
        exit 1
    fi
    
    # 设置 Gemini base URL
    export GEMINI_BASE_URL=${GEMINI_BASE_URL:-"https://apius.tu-zi.com"}
    
    # 检查 PostgreSQL 是否运行
    if ! docker ps | grep -q ashareinsight-postgres; then
        log_warning "PostgreSQL container is not running"
        echo "Starting PostgreSQL..."
        cd docker && docker-compose up -d postgres && cd ..
        sleep 5  # 等待数据库启动
    fi
}

# 解析命令行参数
DOCUMENT_TYPE="all"
FORCE_REPROCESS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --type)
            DOCUMENT_TYPE="$2"
            shift 2
            ;;
        --force)
            FORCE_REPROCESS=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --type [all|annual|research]  Document type to process (default: all)"
            echo "  --force                       Force reprocess all files"
            echo "  --help                        Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# 主函数
main() {
    log_info "Starting incremental extraction process..."
    
    # 检查环境
    check_environment
    
    # 统计信息
    TOTAL_NEW_FILES=0
    TOTAL_PROCESSED=0
    TOTAL_FAILED=0
    
    # 处理年报
    if [ "$DOCUMENT_TYPE" = "all" ] || [ "$DOCUMENT_TYPE" = "annual" ]; then
        log_info "Scanning for new annual reports..."
        
        # 创建已处理文件列表
        PROCESSED_LIST="/tmp/processed_annual_reports.txt"
        if [ "$FORCE_REPROCESS" = true ]; then
            rm -f "$PROCESSED_LIST"
            touch "$PROCESSED_LIST"
        else
            # 从数据库获取已处理文件列表
            uv run python -c "
import asyncio
from sqlalchemy import text
from src.infrastructure.persistence.postgres.connection import get_session

async def get_processed_files():
    async with get_session() as session:
        result = await session.execute(text('''
            SELECT DISTINCT file_path 
            FROM source_documents 
            WHERE doc_type = 'annual_report'
        '''))
        for row in result:
            print(row.file_path)

asyncio.run(get_processed_files())
            " > "$PROCESSED_LIST" 2>/dev/null || touch "$PROCESSED_LIST"
        fi
        
        # 扫描新文件
        NEW_FILES=()
        for file in data/annual_reports/2024/*.md; do
            if [ -f "$file" ]; then
                if ! grep -q "$file" "$PROCESSED_LIST"; then
                    NEW_FILES+=("$file")
                fi
            fi
        done
        
        if [ ${#NEW_FILES[@]} -gt 0 ]; then
            log_info "Found ${#NEW_FILES[@]} new annual reports to process"
            TOTAL_NEW_FILES=$((TOTAL_NEW_FILES + ${#NEW_FILES[@]}))
            
            # 批量处理
            log_info "Processing annual reports..."
            if uv run python -m src.interfaces.cli.batch_extract \
                data/annual_reports/2024 \
                --document-type annual_report \
                --pattern "*.md" \
                --max-files ${#NEW_FILES[@]}; then
                PROCESSED=$((PROCESSED + ${#NEW_FILES[@]}))
                log_success "Annual reports processed successfully"
            else
                log_error "Some annual reports failed to process"
                TOTAL_FAILED=$((TOTAL_FAILED + 1))
            fi
        else
            log_info "No new annual reports found"
        fi
    fi
    
    # 处理研报
    if [ "$DOCUMENT_TYPE" = "all" ] || [ "$DOCUMENT_TYPE" = "research" ]; then
        log_info "Scanning for new research reports..."
        
        # 创建已处理文件列表
        PROCESSED_LIST="/tmp/processed_research_reports.txt"
        if [ "$FORCE_REPROCESS" = true ]; then
            rm -f "$PROCESSED_LIST"
            touch "$PROCESSED_LIST"
        else
            # 从数据库获取已处理文件列表
            uv run python -c "
import asyncio
from sqlalchemy import text
from src.infrastructure.persistence.postgres.connection import get_session

async def get_processed_files():
    async with get_session() as session:
        result = await session.execute(text('''
            SELECT DISTINCT file_path 
            FROM source_documents 
            WHERE doc_type = 'research_report'
        '''))
        for row in result:
            print(row.file_path)

asyncio.run(get_processed_files())
            " > "$PROCESSED_LIST" 2>/dev/null || touch "$PROCESSED_LIST"
        fi
        
        # 扫描新文件
        NEW_FILES=()
        for file in data/research_reports/2024/*.txt; do
            if [ -f "$file" ]; then
                if ! grep -q "$file" "$PROCESSED_LIST"; then
                    NEW_FILES+=("$file")
                fi
            fi
        done
        
        if [ ${#NEW_FILES[@]} -gt 0 ]; then
            log_info "Found ${#NEW_FILES[@]} new research reports to process"
            TOTAL_NEW_FILES=$((TOTAL_NEW_FILES + ${#NEW_FILES[@]}))
            
            # 批量处理
            log_info "Processing research reports..."
            if uv run python -m src.interfaces.cli.batch_extract \
                data/research_reports/2024 \
                --document-type research_report \
                --pattern "*.txt" \
                --max-files ${#NEW_FILES[@]}; then
                PROCESSED=$((PROCESSED + ${#NEW_FILES[@]}))
                log_success "Research reports processed successfully"
            else
                log_error "Some research reports failed to process"
                TOTAL_FAILED=$((TOTAL_FAILED + 1))
            fi
        else
            log_info "No new research reports found"
        fi
    fi
    
    # 生成报告
    log_info "Generating summary report..."
    
    uv run python -c "
import asyncio
from sqlalchemy import text, func
from src.infrastructure.persistence.postgres.connection import get_session
from datetime import datetime, timedelta

async def generate_report():
    async with get_session() as session:
        # 总体统计
        result = await session.execute(text('''
            SELECT 
                doc_type,
                COUNT(*) as count
            FROM source_documents
            GROUP BY doc_type
        '''))
        
        print('\\n=== Database Summary ===')
        total = 0
        for row in result:
            print(f'{row.doc_type}: {row.count} documents')
            total += row.count
        print(f'Total: {total} documents\\n')
        
        # 最近处理的文档
        result = await session.execute(text('''
            SELECT 
                company_code,
                doc_type,
                report_title,
                created_at
            FROM source_documents
            WHERE created_at > :cutoff_time
            ORDER BY created_at DESC
            LIMIT 10
        '''), {'cutoff_time': datetime.now() - timedelta(minutes=10)})
        
        recent = list(result)
        if recent:
            print('=== Recently Processed (last 10 minutes) ===')
            for row in recent:
                print(f'{row.created_at.strftime(\"%H:%M:%S\")} | {row.company_code} | {row.doc_type} | {row.report_title[:50]}...')

asyncio.run(generate_report())
    "
    
    # 最终总结
    echo
    log_info "==================== SUMMARY ===================="
    log_info "Total new files found: $TOTAL_NEW_FILES"
    if [ $TOTAL_NEW_FILES -gt 0 ]; then
        log_success "Successfully processed and archived to database"
    fi
    if [ $TOTAL_FAILED -gt 0 ]; then
        log_warning "Some files failed to process"
    fi
    log_info "=============================================="
}

# 执行主函数
main