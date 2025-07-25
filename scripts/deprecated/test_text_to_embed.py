#!/usr/bin/env python3
"""Test different text_to_embed values for reranking."""

import asyncio

import httpx


async def test_search_with_text_embed(text_to_embed: str, description: str):
    """Test search with specific text_to_embed value."""

    search_payload = {
        "query_identifier": "300257",
        "text_to_embed": text_to_embed,
        "top_k": 50,
        "similarity_threshold": 0.5,
    }

    print(f"\n{'=' * 60}")
    print(f"测试场景: {description}")
    print(f"text_to_embed: {text_to_embed}")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "http://localhost:8000/api/v1/search/similar-companies", json=search_payload
        )

        if response.status_code != 200:
            print(f"搜索失败: {response.status_code}")
            return

        results = response.json()
        companies = results.get("results", [])

        print(f"\n找到 {len(companies)} 家相似公司")
        print("\nTop 10 结果:")

        # 标记关键公司
        key_companies = ["汉钟", "陕鼓", "金通灵", "杭氧", "雪人"]

        for i, company in enumerate(companies[:10]):
            # 检查是否是关键公司
            marker = ""
            for key in key_companies:
                if key in company["company_name"]:
                    marker = f" ⭐ ({key})"
                    break

            print(
                f"{i + 1:2}. {company['company_name'][:25]:25} ({company['company_code']}) "
                f"- Score: {company['relevance_score']:.3f}{marker}"
            )

        # 查找关键公司的排名
        print("\n关键压缩机公司排名:")
        for key in key_companies:
            for i, company in enumerate(companies):
                if key in company["company_name"]:
                    print(f"  {company['company_name'][:25]:25} - 排名: {i + 1}")
                    break


async def main():
    """运行不同的测试场景."""

    test_cases = [
        ("", "空字符串（仅使用公司代码）"),
        ("300257", "仅公司代码"),
        ("开山股份", "仅公司名称"),
        ("压缩机", "单个关键词"),
        ("开山股份 压缩机", "公司名称+主营业务"),
        ("开山股份 压缩机制造 空压机 工业气体", "公司名称+多个业务关键词"),
        ("寻找类似开山股份的压缩机制造企业", "自然语言描述"),
        ("压缩机 空压机 螺杆压缩机 离心压缩机 工业设备", "业务领域关键词组合"),
    ]

    for text_to_embed, description in test_cases:
        await test_search_with_text_embed(text_to_embed, description)
        await asyncio.sleep(0.5)  # 避免请求过快


if __name__ == "__main__":
    print("测试不同的 text_to_embed 值对搜索结果的影响")
    asyncio.run(main())
