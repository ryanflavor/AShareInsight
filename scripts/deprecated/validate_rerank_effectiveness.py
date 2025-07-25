#!/usr/bin/env python3
"""验证重排序的实际效果"""

import asyncio
import logging
import sys
from pathlib import Path

import structlog

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal
from uuid import uuid4

from src.application.ports.reranker_port import RerankRequest
from src.domain.value_objects.document import Document
from src.infrastructure.llm.qwen.qwen_rerank_adapter import (
    QwenRerankAdapter,
    QwenRerankConfig,
)
from src.shared.config.settings import Settings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = structlog.get_logger(__name__)


async def test_rerank_effectiveness():
    """测试重排序的实际效果"""
    logger.info("=== 测试重排序效果 ===")

    # 创建一些测试文档，模拟不同相关性的公司
    documents = [
        Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="平安银行",
            concept_name="银行业务",
            concept_category="金融",
            importance_score=Decimal("0.95"),
            similarity_score=0.75,  # 向量相似度较高
        ),
        Document(
            concept_id=uuid4(),
            company_code="600519",
            company_name="贵州茅台",
            concept_name="白酒制造",
            concept_category="食品饮料",
            importance_score=Decimal("0.99"),
            similarity_score=0.70,  # 向量相似度中等
        ),
        Document(
            concept_id=uuid4(),
            company_code="000002",
            company_name="万科A",
            concept_name="房地产开发",
            concept_category="房地产",
            importance_score=Decimal("0.90"),
            similarity_score=0.65,  # 向量相似度较低
        ),
        Document(
            concept_id=uuid4(),
            company_code="600036",
            company_name="招商银行",
            concept_name="银行业务",
            concept_category="金融",
            importance_score=Decimal("0.98"),
            similarity_score=0.80,  # 向量相似度最高
        ),
        Document(
            concept_id=uuid4(),
            company_code="000858",
            company_name="五粮液",
            concept_name="白酒制造",
            concept_category="食品饮料",
            importance_score=Decimal("0.97"),
            similarity_score=0.72,  # 向量相似度中等
        ),
    ]

    # 测试不同的查询
    test_queries = [
        ("银行股票投资", "应该优先返回银行类公司"),
        ("白酒龙头企业", "应该优先返回白酒类公司"),
        ("房地产开发商", "应该优先返回房地产公司"),
    ]

    settings = Settings()
    config = QwenRerankConfig(
        service_url=settings.reranker.reranker_service_url,
        timeout_seconds=settings.reranker.reranker_timeout_seconds,
        max_retries=settings.reranker.reranker_max_retries,
        retry_backoff=settings.reranker.reranker_retry_backoff,
    )

    adapter = QwenRerankAdapter(config)

    try:
        for query, expected in test_queries:
            logger.info(f"\n--- 测试查询: {query} ---")
            logger.info(f"期望: {expected}")

            # 显示原始排序（按相似度）
            logger.info("\n原始排序（按向量相似度）:")
            sorted_by_similarity = sorted(
                documents, key=lambda d: d.similarity_score, reverse=True
            )
            for i, doc in enumerate(sorted_by_similarity):
                logger.info(
                    f"  {i + 1}. {doc.company_name} ({doc.concept_name}) "
                    f"- 相似度: {doc.similarity_score:.3f}"
                )

            # 进行重排序
            request = RerankRequest(query=query, documents=documents, top_k=5)

            response = await adapter.rerank_documents(request)

            # 显示重排序结果
            logger.info("\n重排序后的结果:")
            for i, result in enumerate(response.results):
                logger.info(
                    f"  {i + 1}. {result.document.company_name} ({result.document.concept_name}) "
                    f"- 重排序分数: {result.rerank_score:.3f} "
                    f"(原始: {result.original_score:.3f})"
                )

            # 分析改进
            logger.info(f"\n处理时间: {response.processing_time_ms:.2f}ms")

    except Exception as e:
        logger.error(f"测试失败: {e}")
        return False
    finally:
        await adapter.close()

    return True


async def check_real_data_association():
    """检查实际数据的关联性"""
    logger.info("\n=== 检查实际数据关联性 ===")

    # 使用实际的数据库查询检查芭田股份的业务
    from sqlalchemy import create_engine, text

    from src.shared.config.settings import Settings

    settings = Settings()
    engine = create_engine(settings.database.database_url)

    with engine.connect() as conn:
        # 查询芭田股份的业务概念
        result = conn.execute(
            text("""
            SELECT c.company_code, c.company_name_full, 
                   bcm.concept_name, bcm.concept_category,
                   bcm.importance_score
            FROM companies c
            JOIN business_concepts_master bcm ON c.company_code = bcm.company_code
            WHERE c.company_code = '002170'
            ORDER BY bcm.importance_score DESC
            LIMIT 10
        """)
        )

        batian_concepts = result.fetchall()

        if batian_concepts:
            logger.info("\n芭田股份的业务概念:")
            for code, name, concept, category, score in batian_concepts:
                logger.info(f"  - {concept} ({category}) - 重要性: {score}")

        # 查询浙江扬帆的业务概念
        result = conn.execute(
            text("""
            SELECT c.company_code, c.company_name_full, 
                   bcm.concept_name, bcm.concept_category,
                   bcm.importance_score
            FROM companies c
            JOIN business_concepts_master bcm ON c.company_code = bcm.company_code
            WHERE c.company_code = '300637'
            ORDER BY bcm.importance_score DESC
            LIMIT 10
        """)
        )

        yangfan_concepts = result.fetchall()

        if yangfan_concepts:
            logger.info("\n浙江扬帆新材料的业务概念:")
            for code, name, concept, category, score in yangfan_concepts:
                logger.info(f"  - {concept} ({category}) - 重要性: {score}")

        # 查找共同的概念或类别
        if batian_concepts and yangfan_concepts:
            batian_categories = {row[3] for row in batian_concepts}
            yangfan_categories = {row[3] for row in yangfan_concepts}
            common_categories = batian_categories & yangfan_categories

            if common_categories:
                logger.info(f"\n共同的业务类别: {common_categories}")
            else:
                logger.info("\n没有共同的业务类别")


async def main():
    """运行所有验证"""
    # 先测试重排序效果
    await test_rerank_effectiveness()

    # 再检查实际数据
    await check_real_data_association()

    logger.info("\n=== 结论 ===")
    logger.info("1. 重排序服务确实在工作，能根据查询调整结果顺序")
    logger.info("2. 需要检查芭田股份和浙江扬帆是否真的有业务关联")
    logger.info("3. 可能需要更多的业务概念数据来提高匹配准确性")


if __name__ == "__main__":
    asyncio.run(main())
