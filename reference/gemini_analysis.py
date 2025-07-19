import json
import os

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def load_prompt():
    """Load the prompt from prompt.md"""
    with open(
        "/home/ryan/workspace/github/AShareInsight/reference/prompt/prompt_a.md",
        encoding="utf-8",
    ) as f:
        return f.read()


def call_gemini_api(prompt, document_content):
    """Call Gemini API with custom endpoint support"""

    # Configure the API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")

    # Check if using custom API endpoint
    base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")

    # Format the complete prompt with document content
    complete_prompt = prompt.replace("[请填写公司名称]", "待分析公司")
    complete_prompt = complete_prompt.replace(
        "[请填写文档类型，如：2024年年度报告摘要]", "年度报告"
    )
    complete_prompt = complete_prompt.replace(
        "[请在此处粘贴您需要分析的文档全文]", document_content
    )

    # Use custom API endpoint with retries
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": "gemini-2.5-pro-preview-06-05",
        "messages": [{"role": "user", "content": complete_prompt}],
        "max_tokens": 30000,
        "temperature": 1.0,
    }

    # Retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(
                f"正在调用API (第{attempt + 1}次尝试): {base_url}/v1/chat/completions"
            )
            response = requests.post(
                f"{base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                print(f"✅ API调用成功，响应长度: {len(content)}")
                return content
            else:
                print(f"API请求失败: {response.status_code} - {response.text}")
                if attempt < max_retries - 1:
                    print("正在重试...")
                    continue
                else:
                    raise Exception(
                        f"API调用失败: {response.status_code} - {response.text}"
                    )

        except requests.exceptions.Timeout:
            print(f"请求超时 (第{attempt + 1}次尝试)")
            if attempt < max_retries - 1:
                print("正在重试...")
                continue
            else:
                raise Exception("请求超时，已重试3次")
        except Exception as e:
            print(f"API调用异常: {e}")
            if attempt < max_retries - 1:
                print("正在重试...")
                continue
            else:
                raise Exception(f"API调用失败: {e}")


def main():
    """Main function to run the analysis"""
    try:
        # Load the prompt template
        prompt_template = load_prompt()

        # Example usage - you can replace this with actual document content
        document_content = """
        请在这里输入您要分析的年度报告内容...
        """

        with open(
            "/home/ryan/workspace/github/AShareInsight/reference/inputs/开山股份_2024年年度报告摘要.md",
            encoding="utf-8",
        ) as f:
            document_content = f.read()

        print("正在调用 Gemini 2.5 Pro 模型...")

        # Call the API
        result = call_gemini_api(prompt_template, document_content)

        # Try to parse as JSON to validate format
        try:
            # Check if the result is wrapped in markdown code blocks
            if result.strip().startswith("```"):
                # Extract JSON from markdown code blocks
                lines = result.strip().split("\n")
                # Find the start and end of the JSON content
                start_idx = 0
                end_idx = len(lines)

                for i, line in enumerate(lines):
                    if line.strip().startswith("```json") or line.strip() == "```":
                        start_idx = i + 1
                        break

                for i in range(len(lines) - 1, -1, -1):
                    if lines[i].strip() == "```":
                        end_idx = i
                        break

                # Extract the JSON content
                json_content = "\n".join(lines[start_idx:end_idx])
                parsed_result = json.loads(json_content)
            else:
                # Direct JSON parsing
                parsed_result = json.loads(result)

            print("✅ 成功获得格式正确的JSON响应")
            print(json.dumps(parsed_result, ensure_ascii=False, indent=2))

            # Save the parsed result to a file
            output_path = "/home/ryan/workspace/github/AShareInsight/output/gemini_analysis_result.json"
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(parsed_result, f, ensure_ascii=False, indent=2)
            print(f"\n✅ 结果已保存到: {output_path}")

        except json.JSONDecodeError as e:
            print(f"⚠️  JSON解析失败: {e}")
            print("原始响应：")
            print(result)

    except Exception as e:
        print(f"❌ 错误: {e}")


if __name__ == "__main__":
    main()
