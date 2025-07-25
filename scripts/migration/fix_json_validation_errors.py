#!/usr/bin/env python3
"""
修复提取文件中的JSON验证错误
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

console = Console()


def fix_established_year(data: dict[str, Any]) -> bool:
    """修复established字段的类型错误（int -> str）"""
    fixed = False

    if "extraction_data" in data and "business_concepts" in data["extraction_data"]:
        for concept in data["extraction_data"]["business_concepts"]:
            if "timeline" in concept and concept["timeline"]:
                if "established" in concept["timeline"]:
                    value = concept["timeline"]["established"]
                    if isinstance(value, int):
                        concept["timeline"]["established"] = str(value)
                        fixed = True

    return fixed


def fix_none_timelines(data: dict[str, Any]) -> bool:
    """修复timeline为None的问题"""
    fixed = False

    if "extraction_data" in data and "business_concepts" in data["extraction_data"]:
        for concept in data["extraction_data"]["business_concepts"]:
            if "timeline" not in concept or concept["timeline"] is None:
                # 创建一个默认的timeline
                concept["timeline"] = {"established": "未知", "evolution": "信息不详"}
                fixed = True

    return fixed


def fix_company_code(data: dict[str, Any], filename: str) -> bool:
    """修复缺失的公司代码"""
    fixed = False

    if "extraction_data" in data:
        if not data["extraction_data"].get("company_code"):
            # 尝试从文件名提取公司代码
            # 通常文件名格式类似: 百甲科技_2024年年度报告摘要.md
            match = re.search(r"(\d{6})", filename)
            if match:
                data["extraction_data"]["company_code"] = match.group(1)
                fixed = True
            else:
                # 如果文件名没有代码，设置为"UNKNOWN"
                data["extraction_data"]["company_code"] = "UNKNOWN"
                fixed = True
                console.print(
                    "  [yellow]警告: 无法从文件名提取公司代码，设置为UNKNOWN[/yellow]"
                )

    return fixed


def fix_concept_category(data: dict[str, Any]) -> bool:
    """修复concept_category不符合枚举值的问题"""
    fixed = False
    valid_categories = ["核心业务", "新兴业务", "战略布局"]

    if "extraction_data" in data and "business_concepts" in data["extraction_data"]:
        for concept in data["extraction_data"]["business_concepts"]:
            if "concept_category" in concept:
                if concept["concept_category"] not in valid_categories:
                    # 根据原值猜测正确的类别
                    original = concept["concept_category"]
                    if "成长" in original or "新" in original:
                        concept["concept_category"] = "新兴业务"
                    elif "核心" in original or "主" in original:
                        concept["concept_category"] = "核心业务"
                    else:
                        concept["concept_category"] = "战略布局"
                    fixed = True
            elif "concept_name" in concept:
                # 缺失concept_category字段
                concept["concept_category"] = "核心业务"
                fixed = True

    return fixed


def fix_company_name(data: dict[str, Any], filename: str) -> bool:
    """修复缺失的公司名称"""
    fixed = False

    if "extraction_data" in data:
        if not data["extraction_data"].get("company_name_full"):
            # 从文件名提取公司名称
            company_name = filename.split("_")[0]
            data["extraction_data"]["company_name_full"] = f"{company_name}股份有限公司"
            data["extraction_data"]["company_name_short"] = company_name
            fixed = True

    return fixed


def process_extraction_file(json_path: Path, checkpoint_path: Path) -> bool:
    """处理单个提取文件"""
    try:
        # 读取JSON文件
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        # 读取checkpoint以获取错误信息
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)

        error = checkpoint.get("stages", {}).get("extraction", {}).get("error", "")

        # 只处理验证错误，不处理配额错误
        if "Validation failed:" not in error or "insufficient_user_quota" in error:
            return False

        console.print(f"\n处理文件: {json_path.name}")

        # 应用修复
        fixed = False
        filename = checkpoint.get("file_path", "").split("/")[-1]

        if "company_code" in error and "should be a valid string" in error:
            if fix_company_code(data, filename):
                console.print("  ✅ 修复了company_code")
                fixed = True

        if "timeline" in error and "input_value=None" in error:
            if fix_none_timelines(data):
                console.print("  ✅ 修复了timeline为None的问题")
                fixed = True

        if "established" in error and "input_type=int" in error:
            if fix_established_year(data):
                console.print("  ✅ 修复了established年份类型")
                fixed = True

        if "concept_category" in error:
            if fix_concept_category(data):
                console.print("  ✅ 修复了concept_category枚举值")
                fixed = True

        if "company_name_full" in error:
            if fix_company_name(data, filename):
                console.print("  ✅ 修复了公司名称")
                fixed = True

        # 如果有修复，保存文件
        if fixed:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 更新checkpoint状态为pending，以便重试
            checkpoint["stages"]["extraction"]["status"] = "success"
            checkpoint["stages"]["extraction"]["error"] = None
            checkpoint["stages"]["archive"]["status"] = "pending"

            with open(checkpoint_path, "w") as f:
                json.dump(checkpoint, f, indent=2)

        return fixed

    except Exception as e:
        console.print(f"  ❌ 处理失败: {e}")
        return False


@click.command()
@click.option("--dry-run", is_flag=True, help="只检查不修复")
@click.option("--limit", default=-1, help="限制处理文件数")
def main(dry_run: bool, limit: int):
    """修复JSON验证错误"""

    checkpoint_dir = Path("data/temp/checkpoints")
    fixed_count = 0
    processed_count = 0

    # 查找所有需要修复的文件
    files_to_fix = []

    for cp_file in checkpoint_dir.glob("*.json"):
        try:
            with open(cp_file) as f:
                checkpoint = json.load(f)

            extraction = checkpoint.get("stages", {}).get("extraction", {})
            if extraction.get("status") == "failed":
                error = extraction.get("error", "")
                if (
                    "Validation failed:" in error
                    and "insufficient_user_quota" not in error
                ):
                    # 获取提取文件路径
                    output_path = extraction.get("output_path")
                    if output_path and Path(output_path).exists():
                        files_to_fix.append((Path(output_path), cp_file))
        except:
            pass

    console.print(f"找到 {len(files_to_fix)} 个需要修复的文件")

    if dry_run:
        console.print("\n[yellow]DRY RUN - 只显示需要修复的文件[/yellow]")
        for json_path, cp_path in files_to_fix[:10]:
            console.print(f"  - {json_path.name}")
        if len(files_to_fix) > 10:
            console.print(f"  ... 还有 {len(files_to_fix) - 10} 个")
        return

    # 处理文件
    to_process = files_to_fix[:limit] if limit > 0 else files_to_fix

    for json_path, checkpoint_path in to_process:
        if process_extraction_file(json_path, checkpoint_path):
            fixed_count += 1
        processed_count += 1

    console.print(f"\n处理完成: {fixed_count}/{processed_count} 个文件已修复")

    if fixed_count > 0:
        console.print(
            "\n[green]已修复的文件可以使用 resume_pending_files.py 重新归档[/green]"
        )


if __name__ == "__main__":
    main()
