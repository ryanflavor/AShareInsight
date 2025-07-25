#!/usr/bin/env python3
"""
创建file_path索引 - 单独运行避免事务问题
"""

import asyncio
import sys
from pathlib import Path

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.shared.config.settings import Settings

logger = structlog.get_logger(__name__)


async def create_index():
    """创建file_path索引"""
    settings = Settings()

    # 构建数据库URL
    from sqlalchemy.engine.url import URL

    db_settings = settings.database
    database_url = URL.create(
        drivername="postgresql+asyncpg",
        username=db_settings.postgres_user,
        password=db_settings.postgres_password.get_secret_value(),
        host=db_settings.postgres_host,
        port=db_settings.postgres_port,
        database=db_settings.postgres_db,
    ).render_as_string(hide_password=False)

    # 直接创建引擎，设置isolation_level为AUTOCOMMIT
    engine = create_async_engine(
        database_url,
        echo=False,
        isolation_level="AUTOCOMMIT",  # 避免事务
    )

    async with engine.connect() as conn:
        try:
            # 检查索引是否已存在
            check_query = text("""
                SELECT COUNT(*) 
                FROM pg_indexes 
                WHERE indexname = 'idx_source_documents_file_path'
            """)
            result = await conn.execute(check_query)
            exists = result.scalar() > 0

            if exists:
                logger.info("索引已存在，跳过创建")
                return

            # 创建索引
            logger.info("创建file_path索引...")
            create_query = text("""
                CREATE INDEX CONCURRENTLY idx_source_documents_file_path
                ON source_documents (file_path)
                WHERE file_path IS NOT NULL
            """)
            await conn.execute(create_query)

            logger.info("✅ 成功创建file_path索引")

        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_index())
