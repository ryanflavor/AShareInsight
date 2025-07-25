#!/usr/bin/env python3
"""
处理涨停公司并生成市场过滤后的相似公司报告（单Excel文件版）

该脚本读取包含涨停公司的Excel文件，对每个公司执行相似性搜索，
应用市场过滤器（L = X * (S + V)评分），并将所有结果输出到一个Excel文件的不同分页中。
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx
import pandas as pd
import structlog
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.shared.config.settings import settings
from src.shared.utils.timezone import now_china

# Load environment variables
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = structlog.get_logger(__name__)


class CompanySearchResult(BaseModel):
    """公司搜索结果模型"""

    company_code: str
    company_name: str
    relevance_score: float = Field(description="相关性得分")
    market_cap: float | None = Field(None, description="市值（元）")
    avg_volume_5d: float | None = Field(None, description="5日平均成交量（元）")
    market_cap_score: float | None = Field(None, description="市值评分S")
    volume_score: float | None = Field(None, description="成交量评分V")
    final_score: float | None = Field(None, description="最终得分L = X * (S + V)")
    match_reason: str = Field(description="匹配原因")


class MarketFilteredSearcher:
    """市场过滤搜索器"""

    def __init__(self, api_base_url: str = None):
        """初始化搜索器

        Args:
            api_base_url: API基础URL，默认从配置读取
        """
        self.api_base_url = api_base_url or f"http://localhost:{settings.api.api_port}"
        self.client = httpx.AsyncClient(timeout=30.0)
        self._market_data_cache = {}

    async def __aenter__(self):
        # Initialize market data repository
        import asyncpg

        db_config = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "ashareinsight_db"),
            "user": os.getenv("POSTGRES_USER", "ashareinsight"),
            "password": os.getenv("POSTGRES_PASSWORD", "ashareinsight_password"),
        }

        self.db_pool = await asyncpg.create_pool(**db_config, min_size=2, max_size=10)

        from src.infrastructure.persistence.postgres.market_data_repository import (
            MarketDataRepository as PostgresMarketDataRepo,
        )
        from src.infrastructure.persistence.postgres.market_data_repository_adapter import (
            PostgresMarketDataRepositoryAdapter,
        )

        postgres_repo = PostgresMarketDataRepo(self.db_pool)
        self.market_repo = PostgresMarketDataRepositoryAdapter(postgres_repo)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
        if hasattr(self, "db_pool"):
            await self.db_pool.close()

    async def get_market_data(self, company_codes: list[str]) -> dict:
        """获取公司的市场数据

        Args:
            company_codes: 公司代码列表

        Returns:
            公司代码到市场数据的映射
        """
        # Check cache first
        uncached_codes = [
            code for code in company_codes if code not in self._market_data_cache
        ]

        if uncached_codes:
            # Fetch from database
            market_data = await self.market_repo.get_market_data(uncached_codes)

            # Update cache
            for code, data in market_data.items():
                self._market_data_cache[code] = data

        # Return requested data from cache
        return {
            code: self._market_data_cache.get(code)
            for code in company_codes
            if code in self._market_data_cache
        }

    def calculate_scores(
        self, relevance_score: float, market_cap: float, volume: float
    ) -> dict:
        """计算市场评分

        Args:
            relevance_score: 相关性得分 (0-1)
            market_cap: 市值（元）
            volume: 成交量（元）

        Returns:
            包含各项评分的字典
        """
        from src.shared.config.market_filter_config import MarketFilterConfig

        config = MarketFilterConfig()

        # X - 相关性系数
        x = relevance_score

        # S - 市值评分
        s = config.get_market_cap_score(market_cap)

        # V - 成交量评分
        v = config.get_volume_score(volume)

        # L = X * (S + V)
        l = x * (s + v)

        return {"market_cap_score": s, "volume_score": v, "final_score": l}

    async def search_similar_companies(
        self, company_name: str, company_code: str, limit: int = 100
    ) -> list[CompanySearchResult]:
        """搜索相似公司并应用市场过滤

        Args:
            company_name: 公司名称
            company_code: 公司代码
            limit: 返回结果数量限制

        Returns:
            过滤和评分后的公司列表
        """
        try:
            # 构建搜索查询
            search_query = f"{company_name}"

            # 调用搜索API，不设置市场过滤器以获取更多结果
            response = await self.client.post(
                f"{self.api_base_url}/api/v1/search/similar-companies",
                json={
                    "query_identifier": search_query,
                    "top_k": limit * 2,  # 获取更多结果以便手动过滤
                    "similarity_threshold": 0.45,
                },
            )
            response.raise_for_status()

            data = response.json()

            # 提取所有公司代码
            company_codes = [
                company["company_code"] for company in data.get("results", [])
            ]

            # 批量获取市场数据
            market_data_map = (
                await self.get_market_data(company_codes) if company_codes else {}
            )

            # 解析结果并应用市场过滤
            results = []
            for company in data.get("results", []):
                company_code = company["company_code"]

                # 获取市场数据
                market_data = market_data_map.get(company_code)

                if market_data:
                    market_cap = float(market_data.market_cap_cny)
                    avg_volume = float(market_data.avg_volume_5day)

                    # 应用过滤条件
                    if market_cap > 85e8 or avg_volume > 2e8:
                        continue  # 跳过不符合条件的公司

                    # 计算评分
                    scores = self.calculate_scores(
                        relevance_score=company.get("relevance_score", 0),
                        market_cap=market_cap,
                        volume=avg_volume,
                    )

                    result = CompanySearchResult(
                        company_code=company_code,
                        company_name=company["company_name"],
                        relevance_score=company.get("relevance_score", 0),
                        market_cap=market_cap,
                        avg_volume_5d=avg_volume,
                        market_cap_score=scores["market_cap_score"],
                        volume_score=scores["volume_score"],
                        final_score=scores["final_score"],
                        match_reason=self._format_match_reason(company),
                    )
                else:
                    # 没有市场数据的公司
                    result = CompanySearchResult(
                        company_code=company_code,
                        company_name=company["company_name"],
                        relevance_score=company.get("relevance_score", 0),
                        market_cap=None,
                        avg_volume_5d=None,
                        market_cap_score=None,
                        volume_score=None,
                        final_score=0,  # 没有市场数据的公司得分为0
                        match_reason=self._format_match_reason(company),
                    )

                results.append(result)

            # 按最终得分排序
            results.sort(key=lambda x: x.final_score or 0, reverse=True)

            # 限制返回数量
            return results[:limit]

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP错误 {e.response.status_code}: {e.response.text}")
            logger.error(f"搜索{company_name}({company_code})失败")
            return []
        except Exception as e:
            logger.error(f"搜索{company_name}({company_code})失败: {e}")
            return []

    def _format_match_reason(self, company_data: dict) -> str:
        """格式化匹配原因

        Args:
            company_data: 公司数据

        Returns:
            格式化的匹配原因
        """
        concepts = company_data.get("matched_concepts", [])
        if not concepts:
            return "无匹配概念"

        # 取得分最高的前3个概念
        top_concepts = concepts[:3]

        reasons = []
        for concept in top_concepts:
            name = concept.get("name", "")
            score = concept.get("similarity_score", 0)
            reasons.append(f"{name}(相关度:{score:.2f})")

        return "; ".join(reasons)


def format_dataframe(df: pd.DataFrame, source_company: str) -> pd.DataFrame:
    """格式化数据框

    Args:
        df: 原始数据框
        source_company: 查询公司信息

    Returns:
        格式化后的数据框
    """
    # 添加原始公司信息
    df["source_company"] = source_company
    df["search_time"] = now_china().strftime("%Y-%m-%d %H:%M:%S")

    # 格式化数值列
    # First rename the columns that need unit conversion
    if "market_cap" in df.columns:
        df["市值(亿元)"] = pd.to_numeric(df["market_cap"], errors="coerce") / 1e8
        df.drop("market_cap", axis=1, inplace=True)

    if "avg_volume_5d" in df.columns:
        df["5日均成交量(亿元)"] = (
            pd.to_numeric(df["avg_volume_5d"], errors="coerce") / 1e8
        )
        df.drop("avg_volume_5d", axis=1, inplace=True)

    # Format other numeric columns
    for col in ["relevance_score", "market_cap_score", "volume_score", "final_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(3)

    # 重命名列为中文
    column_mapping = {
        "company_code": "股票代码",
        "company_name": "公司名称",
        "relevance_score": "相关性得分(X)",
        "market_cap_score": "市值评分(S)",
        "volume_score": "成交量评分(V)",
        "final_score": "最终得分(L)",
        "match_reason": "匹配原因",
        "source_company": "查询公司",
        "search_time": "查询时间",
    }
    df.rename(columns=column_mapping, inplace=True)

    # 选择输出列
    output_columns = [
        "股票代码",
        "公司名称",
        "相关性得分(X)",
        "市值(亿元)",
        "5日均成交量(亿元)",
        "市值评分(S)",
        "成交量评分(V)",
        "最终得分(L)",
        "匹配原因",
        "查询公司",
        "查询时间",
    ]

    # 确保所有列都存在
    output_columns = [col for col in output_columns if col in df.columns]
    return df[output_columns]


async def process_companies(
    searcher: MarketFilteredSearcher, companies_df: pd.DataFrame
) -> dict:
    """处理所有公司并返回结果字典

    Args:
        searcher: 搜索器实例
        companies_df: 包含公司信息的DataFrame

    Returns:
        字典，key为sheet名称，value为DataFrame
    """
    all_results = {}

    for idx, row in companies_df.iterrows():
        company_code = row["股票代码"]
        company_name = row["股票简称"]

        logger.info(
            f"正在处理 ({idx + 1}/{len(companies_df)}): {company_name}({company_code})"
        )

        try:
            # 搜索相似公司
            results = await searcher.search_similar_companies(
                company_name=company_name,
                company_code=company_code,
                limit=100,
            )

            if not results:
                logger.warning(f"{company_name}没有找到符合条件的相似公司")
                continue

            # 转换为DataFrame
            df = pd.DataFrame([r.model_dump() for r in results])

            # 格式化数据
            df = format_dataframe(df, f"{company_name}({company_code})")

            # 生成sheet名称（最多31个字符，Excel限制）
            sheet_name = f"{company_code}_{company_name}"[:31]

            # 确保sheet名称唯一
            if sheet_name in all_results:
                sheet_name = f"{company_code}_{idx}"[:31]

            all_results[sheet_name] = df

            logger.info(f"  - 找到 {len(df)} 家符合条件的相似公司")

        except Exception as e:
            logger.error(f"处理{company_name}时出错: {e}", exc_info=True)

        # 处理间隔，避免过载
        await asyncio.sleep(0.5)

    return all_results


async def main():
    """主函数"""
    # 输入输出路径
    input_file = Path("sample/连续涨停天数大于1的非ST.xlsx")
    output_dir = Path("sample/output")

    # 检查API是否可用
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://localhost:{settings.api.api_port}/health"
            )
            response.raise_for_status()
            logger.info("API服务正常运行")
    except Exception as e:
        logger.error(f"API服务不可用: {e}")
        logger.error("请先启动API服务: uv run python -m src.interfaces.api.main")
        return

    # 检查输入文件
    if not input_file.exists():
        logger.error(f"输入文件不存在: {input_file}")
        return

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 读取输入文件
    logger.info(f"读取输入文件: {input_file}")
    companies_df = pd.read_excel(input_file)
    logger.info(f"找到{len(companies_df)}家公司待处理")

    # 创建搜索器并处理所有公司
    async with MarketFilteredSearcher() as searcher:
        all_results = await process_companies(searcher, companies_df)

    # 生成输出文件名
    timestamp = now_china().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"相似公司分析_市场过滤_{timestamp}.xlsx"

    # 保存到单个Excel文件的多个sheet
    if all_results:
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            # 首先创建汇总sheet
            summary_data = []
            for sheet_name, df in all_results.items():
                company_info = df["查询公司"].iloc[0] if len(df) > 0 else sheet_name
                summary_data.append(
                    {
                        "Sheet名称": sheet_name,
                        "查询公司": company_info,
                        "找到相似公司数": len(df),
                        "最高得分": df["最终得分(L)"].max() if len(df) > 0 else 0,
                        "平均得分": df["最终得分(L)"].mean() if len(df) > 0 else 0,
                    }
                )

            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name="汇总", index=False)

            # 调整汇总sheet的列宽
            worksheet = writer.sheets["汇总"]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

            # 写入各公司数据
            for sheet_name, df in all_results.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)

                # 调整列宽
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width

        logger.info("\n✅ 处理完成！")
        logger.info(f"输出文件: {output_file}")
        logger.info(f"包含 {len(all_results)} 个公司的分析结果")
    else:
        logger.warning("没有生成任何结果")

    # 生成处理报告
    report_file = output_dir / f"处理报告_{timestamp}.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"处理时间: {now_china()}\n")
        f.write(f"输入文件: {input_file}\n")
        f.write(f"总公司数: {len(companies_df)}\n")
        f.write(f"成功处理: {len(all_results)}\n")
        f.write(f"失败数量: {len(companies_df) - len(all_results)}\n\n")
        f.write("处理详情:\n")
        for sheet_name, df in all_results.items():
            f.write(f"- {sheet_name}: {len(df)} 家相似公司\n")


if __name__ == "__main__":
    asyncio.run(main())
