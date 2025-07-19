# **5. API详细契约**

此契约将由`interfaces/api/v1/`模块负责实现，其中请求和响应的Pydantic模型将定义在`schemas/`子目录中。

## **Endpoint: `POST /api/v1/search/similar-companies`**

  * **描述**: 根据输入的核心公司，检索并返回业务概念上相关的其他上市公司列表。
  * **查询参数 (Query Parameters)**:
      * `include_justification` (boolean, optional, default: `false`): **【新增】** 是否在返回结果中包含详细的匹配理由和溯源证据。

## **5.1 请求体 (Request Body)**

  * **Content-Type**: `application/json`

| 字段名 | 数据类型 | 是否必需 | 描述 |
| :--- | :--- | :--- | :--- |
| `query_identifier` | `string` | **是** | 要查询的公司简称或股票代码 (例如: "华润微" 或 "688396")。 |
| `top_k` | `integer` | 否 (默认: 20) | 希望返回的相关公司数量上限。 |
| `market_filters` | `object` | 否 | 行情数据过滤器，用于对最终结果进行筛选。 |
|  L `max_market_cap_cny` | `integer` | 否 | **最大市值** (人民币)。只返回市值低于此值的公司。 |
| L `min_5day_avg_volume` | `integer` | 否 | **最小5日平均成交额**。只返回近期成交额高于此值的公司。 |

**请求示例:**

```json
{
  "query_identifier": "开立医疗",
  "top_k": 10,
  "market_filters": {
    "max_market_cap_cny": 50000000000
  }
}
```

## **5.2 成功响应 (Success Response)**

  * **Code**: `200 OK`
  * **Content-Type**: `application/json`

| 字段名 | 数据类型 | 描述 |
| :--- | :--- | :--- |
| `query_company`| `object` | 本次查询的核心公司信息。 |
| L `name` | `string` | 公司简称。 |
| L `code` | `string` | 公司代码。 |
| `metadata` | `object` | **【新增】** 关于本次查询的元数据。 |
| L `total_results_before_limit` | `integer`| 在应用`top_k`限制前，找到的相关公司总数。 |
| L `filters_applied` | `object` | 本次查询实际生效的过滤器。 |
| `results` | `array` of `object` | 相关公司列表，按`relevance_score`降序排列。 |
| L `company_name`| `string` | 相关公司的简称。 |
| L `company_code`| `string` | 相关公司的代码。 |
| L `relevance_score`| `float` | 综合相关性评分 (0-1)。 |
| L `matched_concepts`| `array` of `object` | 匹配到的核心业务概念列表。 |
|     L `name` | `string` | 匹配到的业务概念名称。 |
|     L `similarity_score` | `float` | 该概念与源公司概念的相似度分数。 |
| L `justification`| `object` | **【变为可选】** 仅当`include_justification=true`时才会出现。 |
|     L `summary` | `string` | 自动生成的简明匹配理由。 |
|     L `supporting_evidence` | `array` of `string`| 溯源证据。 |

**响应示例 (当`include_justification=true`时):**

```json
{
  "query_company": {
    "name": "开立医疗",
    "code": "300633"
  },
  "metadata": {
    "total_results_before_limit": 152,
    "filters_applied": {
      "max_market_cap_cny": 50000000000
    }
  },
  "results": [
    {
      "company_name": "迈瑞医疗",
      "company_code": "300760",
      "relevance_score": 0.89,
      "matched_concepts": [
        { "name": "超声业务", "similarity_score": 0.92 },
        { "name": "内镜业务", "similarity_score": 0.85 }
      ],
      "justification": {
        "summary": "因在[超声业务]、[内镜业务]等核心业务上高度重叠而相关。",
        "supporting_evidence": [
          "迈瑞医疗：公司超声影像产品线齐全...",
          "开立医疗：超声板块高端S80/P80系列正式推出..."
        ]
      }
    }
  ]
}
```

## **5.3 错误响应 (Error Responses)**

  * **Code**: `404 Not Found`: 传入的`query_identifier`在数据库中找不到对应的公司。
  * **Code**: `422 Unprocessable Entity`: 请求体中的参数类型错误。
  * **Code**: `500 Internal Server Error`: 服务器内部发生未知错误。

-----

Winston在此。收到`*doc-out`指令。

我们继续构建《架构文档》，现在是**第六部分：基础设施与部署策略**。

我将融合我们之前关于私有化部署的详细讨论和优化方案中的最佳实践，为您提供一份完整的、可执行的方案。

-----
