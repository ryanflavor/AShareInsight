"""Test fixtures data for vector search integration tests.

This module provides test data including mock embeddings and
company/concept relationships for testing vector search functionality.
"""

import math
import uuid
from datetime import datetime
from decimal import Decimal


def generate_mock_embedding(seed: int = 0) -> list[float]:
    """Generate a deterministic mock embedding vector.

    Args:
        seed: Seed value for generating different patterns

    Returns:
        List of 2560 float values representing an embedding
    """
    # Create a deterministic pattern based on seed
    embedding = []
    for i in range(2560):
        # Use different patterns for different seeds
        if seed % 3 == 0:
            value = (i + seed) % 100 / 100.0
        elif seed % 3 == 1:
            value = abs(math.sin(i * 0.1 + seed))
        else:
            value = (i * seed % 100) / 100.0
        embedding.append(value)
    return embedding


# Test company data
TEST_COMPANIES = [
    # Financial sector
    ("000001", "平安银行股份有限公司", "金融", True),
    ("600036", "招商银行股份有限公司", "金融", True),
    ("601398", "工商银行股份有限公司", "金融", True),
    # Real estate sector
    ("000002", "万科企业股份有限公司", "房地产", True),
    ("000402", "金融街控股股份有限公司", "房地产", True),
    # Manufacturing sector
    ("000333", "美的集团股份有限公司", "制造业", True),
    ("000651", "格力电器股份有限公司", "制造业", True),
    # Technology sector
    ("002415", "海康威视数字技术股份有限公司", "科技", True),
    ("002230", "科大讯飞股份有限公司", "科技", True),
    # New energy sector
    ("300750", "宁德时代新能源科技股份有限公司", "新能源", True),
    ("002594", "比亚迪股份有限公司", "新能源", True),
]


# Test business concepts with relationships
# Format: (company_code, concept_name, category, importance_score, embedding_seed)
TEST_CONCEPTS = [
    # 平安银行 concepts
    ("000001", "金融科技创新", "金融服务", Decimal("0.90"), 1),
    ("000001", "零售银行业务", "金融服务", Decimal("0.85"), 2),
    ("000001", "对公金融服务", "金融服务", Decimal("0.80"), 3),
    ("000001", "智慧银行建设", "金融服务", Decimal("0.75"), 4),
    # 招商银行 concepts (similar to 平安)
    ("600036", "金融科技应用", "金融服务", Decimal("0.88"), 5),
    ("600036", "财富管理业务", "金融服务", Decimal("0.92"), 6),
    ("600036", "零售金融转型", "金融服务", Decimal("0.85"), 7),
    # 万科 concepts
    ("000002", "房地产开发", "房地产", Decimal("0.95"), 10),
    ("000002", "物业管理服务", "房地产", Decimal("0.75"), 11),
    ("000002", "城市更新项目", "房地产", Decimal("0.70"), 12),
    # 金融街 concepts (similar to 万科)
    ("000402", "商业地产开发", "房地产", Decimal("0.90"), 13),
    ("000402", "物业运营管理", "房地产", Decimal("0.80"), 14),
    # 美的 concepts
    ("000333", "智能家电制造", "制造业", Decimal("0.92"), 20),
    ("000333", "工业自动化", "制造业", Decimal("0.70"), 21),
    ("000333", "智慧家居解决方案", "制造业", Decimal("0.85"), 22),
    # 格力 concepts (similar to 美的)
    ("000651", "空调制造技术", "制造业", Decimal("0.95"), 23),
    ("000651", "智能家电研发", "制造业", Decimal("0.88"), 24),
    ("000651", "新能源技术", "制造业", Decimal("0.65"), 25),
    # 海康威视 concepts
    ("002415", "智能安防系统", "科技", Decimal("0.95"), 30),
    ("002415", "人工智能视觉", "科技", Decimal("0.88"), 31),
    ("002415", "物联网解决方案", "科技", Decimal("0.80"), 32),
    # 科大讯飞 concepts (AI focus)
    ("002230", "语音识别技术", "科技", Decimal("0.93"), 33),
    ("002230", "人工智能应用", "科技", Decimal("0.90"), 34),
    ("002230", "智慧教育方案", "科技", Decimal("0.82"), 35),
    # 宁德时代 concepts
    ("300750", "动力电池制造", "新能源", Decimal("0.96"), 40),
    ("300750", "储能系统解决方案", "新能源", Decimal("0.85"), 41),
    ("300750", "电池回收技术", "新能源", Decimal("0.70"), 42),
    # 比亚迪 concepts (related to 宁德时代)
    ("002594", "新能源汽车制造", "新能源", Decimal("0.94"), 43),
    ("002594", "动力电池技术", "新能源", Decimal("0.88"), 44),
    ("002594", "电动车产业链", "新能源", Decimal("0.85"), 45),
]


def get_test_concept_data() -> list[tuple]:
    """Get formatted test concept data for database insertion.

    Returns:
        List of tuples containing all concept data including generated UUIDs
    """

    concepts_with_ids = []
    for company_code, name, category, importance, seed in TEST_CONCEPTS:
        concept_id = uuid.uuid4()
        embedding = generate_mock_embedding(seed)
        created_at = datetime.utcnow()
        updated_at = created_at

        concepts_with_ids.append(
            (
                concept_id,
                company_code,
                name,
                category,
                float(importance),
                embedding,
                True,  # is_active
                created_at,
                updated_at,
            )
        )

    return concepts_with_ids


# Mock similarity patterns for testing
# These define which companies should be similar based on their sectors
EXPECTED_SIMILARITIES = {
    "000001": ["600036", "601398"],  # 平安银行 similar to other banks
    "000002": ["000402"],  # 万科 similar to 金融街
    "000333": ["000651"],  # 美的 similar to 格力
    "002415": ["002230"],  # 海康威视 similar to 科大讯飞 (both AI/tech)
    "300750": ["002594"],  # 宁德时代 similar to 比亚迪 (both new energy)
}
