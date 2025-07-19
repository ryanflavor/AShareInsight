import os
import json
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from gemini_analysis import load_prompt, call_gemini_api


def process_single_file(input_path):
    """Process a single markdown file and return the result"""
    try:
        # Read the document content
        with open(input_path, "r", encoding="utf-8") as f:
            document_content = f.read()

        # Load the prompt template
        prompt_template = load_prompt()

        # Extract company name from filename
        filename = os.path.basename(input_path)
        company_name = filename.replace("_2024年年度报告摘要.md", "")

        print(f"📄 正在处理: {company_name}")

        # Call the API
        result = call_gemini_api(prompt_template, document_content)

        # Try to parse as JSON, removing markdown code blocks if present
        try:
            # Clean up response - remove markdown code blocks
            clean_result = result.strip()
            if clean_result.startswith("```json"):
                clean_result = clean_result[7:]  # Remove ```json
            if clean_result.endswith("```"):
                clean_result = clean_result[:-3]  # Remove ```
            clean_result = clean_result.strip()

            parsed_result = json.loads(clean_result)
            print(f"✅ {company_name} - 分析完成")
            return {
                "company": company_name,
                "input_file": input_path,
                "success": True,
                "data": parsed_result,
            }
        except json.JSONDecodeError as e:
            print(f"❌ {company_name} - JSON解析失败: {e}")
            return {
                "company": company_name,
                "input_file": input_path,
                "success": False,
                "raw_response": result,
                "error": f"JSON解析失败: {e}",
            }

    except Exception as e:
        print(f"❌ {company_name} - 处理失败: {e}")
        return {
            "company": company_name,
            "input_file": input_path,
            "success": False,
            "error": str(e),
        }


def main():
    """Main batch processing function"""
    # Find all markdown files in inputs directory
    input_files = glob.glob("inputs/*.md")

    if not input_files:
        print("❌ 在inputs目录中未找到.md文件")
        return

    print(f"🔍 发现 {len(input_files)} 个文件待处理")

    # Create outputs directory if it doesn't exist
    os.makedirs("outputs", exist_ok=True)

    # Process files concurrently
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(process_single_file, file_path): file_path
            for file_path in input_files
        }

        # Collect results as they complete
        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)

            # Save individual result
            if result["success"]:
                output_file = f"outputs/{result['company']}_analysis.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result["data"], f, ensure_ascii=False, indent=2)
                print(f"💾 已保存: {output_file}")
            else:
                # Save error log
                error_file = f"outputs/{result['company']}_error.json"
                with open(error_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"⚠️  错误日志: {error_file}")

    # Summary report
    successful = len([r for r in results if r["success"]])
    failed = len(results) - successful

    print("\n📊 处理完成:")
    print(f"   ✅ 成功: {successful} 个文件")
    print(f"   ❌ 失败: {failed} 个文件")

    # Save summary
    summary = {
        "total_files": len(input_files),
        "successful": successful,
        "failed": failed,
        "results": results,
    }

    with open("outputs/batch_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("📋 汇总报告已保存: outputs/batch_summary.json")


if __name__ == "__main__":
    main()
