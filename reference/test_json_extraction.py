import json

# Test the JSON extraction logic
test_response = """```json
{
  "company_name_full": "开山集团股份有限公司",
  "company_name_short": "开山股份",
  "company_code": "300257",
  "exchange": "深圳证券交易所",
  "top_shareholders": [
    {
      "name": "开山控股集团股份有限公司",
      "holding_percentage": 56.98
    }
  ]
}
```"""

print("Testing JSON extraction from markdown code blocks...")

# Extract JSON from markdown code blocks
if test_response.strip().startswith("```"):
    lines = test_response.strip().split("\n")
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
    print(f"Extracted JSON content:\n{json_content}")

    try:
        parsed_result = json.loads(json_content)
        print("\n✅ Successfully parsed JSON!")
        print(json.dumps(parsed_result, ensure_ascii=False, indent=2))
    except json.JSONDecodeError as e:
        print(f"\n❌ Failed to parse JSON: {e}")
