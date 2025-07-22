#!/usr/bin/env python3
"""Debug script to check Qwen Rerank API response format."""

import json

import httpx

# Test rerank endpoint
url = "http://localhost:9547/rerank"
payload = {
    "query": "银行股票投资",
    "documents": [
        "公司名称: 平安银行 | 股票代码: 000001 | 业务概念: 银行业务 | 概念类别: 金融 | 重要性: 0.95",
        "公司名称: 招商银行 | 股票代码: 600036 | 业务概念: 银行业务 | 概念类别: 金融 | 重要性: 0.98",
        "公司名称: 中国平安 | 股票代码: 601318 | 业务概念: 保险业务 | 概念类别: 金融 | 重要性: 0.99",
    ],
    "top_k": 2,
}

print("Sending request to:", url)
print("Payload:", json.dumps(payload, indent=2, ensure_ascii=False))

response = httpx.post(url, json=payload, timeout=10)
print("\nResponse status:", response.status_code)
print("Response body:", json.dumps(response.json(), indent=2, ensure_ascii=False))
