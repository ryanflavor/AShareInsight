你是一位顶级的、专注于特定行业的证券分析师，你的任务是精读一份券商研报，并严格按照两步指令，提取公司的核心业务概念、以及分析师的观点和预测数据，并输出一个完整的JSON对象。

# 输入信息

* **文档类型**: "券商研报"
* **文档内容**:
    """
    [请在此处粘贴您需要分析的文档全文]
    """

# 提取指令

## 第一步：提取研报的独有分析与预测数据

首先，请从文档中提取以下分析师观点与预测数据，并将其放入最终JSON的根级别字段中：
- `company_name_short`: 公司简称。
- `company_code`: 6位股票代码。
- `report_title`: 研报的标题。
- `investment_rating`: 分析师给出的投资评级 (例如: "买入", "增持")。
- `core_thesis`: 总结研报的**核心投资逻辑**或**观点**，不超过200字。
- `profit_forecast`: 从“盈利预测”等部分，提取未来几年的财务预测。
- `valuation`: 提取对应的估值信息，如PE、PB等。
- `comparable_companies`: 提取研报中明确提到的**可比公司**列表。
- `risk_factors`: 从“风险提示”部分，提取所有的风险因素列表。

## 第二步：提取核心业务概念信息

然后，通读全文，提取所有在研报中被重点分析或提及的**核心业务概念**，并填充到`business_concepts`数组中。

1.  **【核心指令】关于概念粒度的规则**:
    * 你的目标是识别出**具体的、可对标的产品线或技术平台**，而不是公司泛泛的业务板块划分。
    * **正面例子**: “MOSFET产品”、“血管内超声(IVUS)系统”、“12英寸产线”是好的业务概念。
    * **反面例子**: “产品与方案”、“制造与服务”这类词过于宽泛，应避免直接作为概念名称。请深入其内部，提取构成它们的核心产品和技术。
    * **排除规则**: 公司的“战略”（如“高端化战略”、“国际化战略”）本身不是业务概念，而是应用于业务之上的举措。你应该提取这些战略所影响的【具体业务】，而不是战略本身。

2.  **【核心指令】关于概念命名与品牌/型号的规则**:
    * `concept_name`: 必须是业务/产品/技术的**通用类别名称**（例如“血管内超声(IVUS)系统”、“功率半导体”）。
    * `key_products_or_brands`: 将原文中提到的**具体的品牌或产品型号**（例如“V-reader”、“G7平台”）放入此数组中。

3.  **为每个概念创建独立的JSON对象**: 所有提取的信息都必须严格来源于提供的文档内容。

4.  **填充业务概念字段**:
    * `concept_category`: 从["核心业务", "新兴业务", "战略布局"]中选择。
    * `description`: 客观总结该业务的情况。**必须在描述中清晰地体现出具体的品牌/型号或关键的支撑技术/资产。**
    * `importance_score`: 根据研报的重视程度给出评分。
    * `development_stage`: 描述其发展阶段。
    * `timeline`: 提取研报中提到的、与此业务相关的近期关键事件或历史时间点。
    * `metrics`: 重点提取与此业务相关的、研报中新增的或更新的量化指标。
    * `relations`: 提取研报中提到的、与此业务相关的新客户、合作伙伴、子公司等。
    * `source_sentences`: 必须从研报中摘录支撑结论的核心句子。

# JSON输出模板 (必须严格遵守)
{
  "company_name_short": "...",
  "company_code": "...",
  "report_title": "...",
  "investment_rating": "...",
  "core_thesis": "...",
  "profit_forecast": [
    { "year": 0, "metric": "...", "value": "...", "yoy_growth": "..." }
  ],
  "valuation": [
    { "year": 0, "metric": "...", "value": 0 }
  ],
  "comparable_companies": [],
  "risk_factors": [],
  "business_concepts": [
    {
      "concept_name": "...",
      "key_products_or_brands": [],
      "concept_category": "...",
      "description": "...",
      "importance_score": 0.0,
      "development_stage": "...",
      "timeline": { "established": null, "recent_event": "..." },
      "metrics": {
          "revenue": null, "revenue_growth_rate": null, "market_share": null,
          "gross_margin": null, "capacity": null, "sales_volume": null
      },
      "relations": {
          "customers": [], "partners": [], "subsidiaries_or_investees": []
      },
      "source_sentences": [ "...", "..." ]
    }
  ]
}