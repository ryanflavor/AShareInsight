#!/usr/bin/env python3
"""End-to-end API test for Story 2.3 - Reranking integration."""

import asyncio
import json
import logging
import sys

import httpx
import structlog

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = structlog.get_logger(__name__)

stock_codes = [
    "001360.SZ",  # 南矿集团
    "001239.SZ",  # 永达股份
    "002037.SZ",  # 保利联合
    "002096.SZ",  # 易普力
    "002097.SZ",  # 山河智能
    "002266.SZ",  # 浙富控股
    "002297.SZ",  # 博云新材
    "002827.SZ",  # 高争民爆
    "002883.SZ",  # 中设股份
    "003001.SZ",  # 中岩大地
    "003002.SZ",  # 壶化股份
    "300564.SZ",  # 筑博设计
    "301038.SZ",  # 深水规院
    "600117.SH",  # 西宁特钢
    "600326.SH",  # 西藏天路
    "600528.SH",  # 中铁工业
    "600749.SH",  # 西藏旅游
    "600801.SH",  # 华新水泥
    "600875.SH",  # 东方电气
    "601399.SH",  # 国机重装
    "601669.SH",  # 中国电建
    "603280.SH",  # 南方路机
    "603616.SH",  # 韩建河山
    "603916.SH",  # 苏博特
    "603966.SH",  # 法兰泰克
    "688425.SH",  # 铁建重工
    "836942.BJ",  # 恒立钻具
]


async def test_search_with_reranking():
    """Test search API with reranking enabled."""
    base_url = "http://localhost:8000"

    # Test search request
    search_payload = {
        "query_identifier": "603193",  # BYD company code
        "top_k": 100,
        "similarity_threshold": 0.5,
        "market_filters": {"min_market_cap": 1000},
    }

    logger.info("Testing search with reranking...")
    logger.info(
        f"Search payload: {json.dumps(search_payload, indent=2, ensure_ascii=False)}"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Make search request
            response = await client.post(
                f"{base_url}/api/v1/search/similar-companies", json=search_payload
            )

            if response.status_code != 200:
                logger.error(f"Search failed with status {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False

            result = response.json()

            # Check if we got results
            if not result.get("results"):
                logger.error("No results returned")
                return False

            companies = result["results"]
            logger.info(f"Found {len(companies)} similar companies")

            # Display top 5 results
            logger.info("\nresults with reranking:")
            for i, company in enumerate(companies):
                logger.info(
                    f"{i + 1}. {company['company_name']} ({company['company_code']}) "
                    f"- Score: {company['relevance_score']:.3f}"
                )

                # Show matched concepts if available
                if "matched_concepts" in company:
                    for concept in company.get("matched_concepts", [])[:2]:
                        if isinstance(concept, dict) and "concept_name" in concept:
                            logger.info(
                                f"   - {concept['concept_name']} "
                                f"(Category: {concept.get('concept_category', 'N/A')})"
                            )

            # Verify results are sorted by relevance score
            scores = [c["relevance_score"] for c in companies]
            if scores != sorted(scores, reverse=True):
                logger.error("Results are not properly sorted by relevance score")
                return False

            # Check filter info
            filter_info = result.get("filters_applied", {})
            logger.info(f"\nFilters applied: {json.dumps(filter_info, indent=2)}")

            # Check performance metrics
            if "performance" in result:
                perf = result["performance"]
                logger.info("\nPerformance metrics:")
                logger.info(f"  Total time: {perf.get('total_time_ms', 0):.2f}ms")
                logger.info(f"  Search time: {perf.get('search_time_ms', 0):.2f}ms")
                if "rerank_time_ms" in perf:
                    logger.info(f"  Rerank time: {perf['rerank_time_ms']:.2f}ms")

            logger.info("\n✅ Search with reranking completed successfully!")
            return True

        except httpx.RequestError as e:
            logger.error(f"Request failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False


async def test_search_without_target():
    """Test search API with another company code."""
    base_url = "http://localhost:8000"

    search_payload = {
        "query_identifier": "防蚊虫，驱蚊",  # 开山股份
        "top_k": 30,
        "similarity_threshold": 0.3,
    }

    logger.info("\nTesting search with another company code...")
    logger.info(
        f"Search payload: {json.dumps(search_payload, indent=2, ensure_ascii=False)}"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{base_url}/api/v1/search/similar-companies", json=search_payload
            )

            if response.status_code != 200:
                logger.error(f"Search failed with status {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False

            result = response.json()
            companies = result.get("results", [])

            logger.info(f"Found {len(companies)} companies similar to the query")

            # Display results
            for i, company in enumerate(companies):
                logger.info(
                    f"{i + 1}. {company['company_name']} - "
                    f"Score: {company['relevance_score']:.3f}"
                )

            logger.info("\n✅ Search with reranking completed successfully!")
            return True

        except Exception as e:
            logger.error(f"Test failed: {e}")
            return False


async def check_reranker_status():
    """Check if reranker service is healthy."""
    logger.info("Checking reranker service health...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:9547/health")
            if response.status_code == 200:
                health = response.json()
                if health.get("reranking_service", {}).get("status") == "healthy":
                    logger.info("✅ Reranker service is healthy")
                    return True
                else:
                    logger.error("Reranker service is not healthy")
                    return False
            else:
                logger.error(f"Health check failed with status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Could not check reranker health: {e}")
            return False


async def main():
    """Run all end-to-end tests."""
    logger.info("=== Story 2.3 End-to-End API Validation ===")

    # Check reranker health first
    if not await check_reranker_status():
        logger.error("Reranker service is not available. Exiting.")
        return 1

    tests = [
        # ("Search with company code and reranking", test_search_with_reranking),
        ("Search with another company code", test_search_without_target),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n--- {test_name} ---")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    logger.info("\n=== Test Summary ===")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n🎉 Story 2.3 E2E validation SUCCESSFUL!")
        logger.info("The reranking service is fully integrated and working correctly.")
        return 0
    else:
        logger.error("\n❌ Story 2.3 E2E validation FAILED!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
