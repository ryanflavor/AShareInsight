"""Annual report extraction prompt templates."""

from .base import BasePrompt


class AnnualReportPromptV1(BasePrompt):
    """Annual report extraction prompt version 1.0.0."""

    def __init__(self):
        """Initialize annual report prompt."""
        super().__init__(
            version="1.0.0",
            description="Initial version for annual report data extraction",
        )

    def _create_template(self) -> str:
        """Create the annual report extraction prompt template."""
        return """你是一位严谨、细致的数据提取专家，你的任务是全面解析一份上市公司年度报告摘要，并严格按照两步指令，提取公司元数据和业务概念信息，最终输出一个完整的、结构化的JSON对象。

# 提取指令

## 第一步：提取公司级元数据

首先，请从文档的"公司基本情况"、"重要提示"或页眉部分，提取以下公司元数据：
- `company_name_full`: 公司完整的官方名称。
- `company_name_short`: 公司在A股市场的简称。
- `company_code`: 公司的6位股票代码。
- `exchange`: 公司股票上市的交易所全称（例如："上海证券交易所"或"深圳证券交易所"）。
- `top_shareholders`: 从"股东情况"部分的"前10名股东持股情况表"中提取。对于每一行，提取"股东名称(全称)"和"持股比例(%)"，并形成一个包含`name`和`holding_percentage`的对象。最多提取10个。

## 第二步：提取业务概念信息

然后，通读全文，提取所有独立的业务概念，并填充到`business_concepts`数组中：
1.  **全面识别并拆分业务概念**: 如果一个业务板块包含多个差异巨大、面向不同市场的子业务（例如，助听器芯片和国产服务器CPU），请将它们拆分为独立的业务概念进行提取。
2.  **为每个概念创建独立的JSON对象**: 所有提取的信息都必须严格来源于提供的文档内容。
3.  **填充业务概念字段**:
    * `concept_name`: 业务概念的通用名称，应简明扼要。
    * `concept_category`: 从["核心业务", "新兴业务", "战略布局"]中选择最恰当的一个。
    * `description`: 使用原文内容，客观总结该业务的具体情况，不超过200字。
    * `importance_score`: 基于该业务在报告中的描述，给出一个0到1.0的综合重要性评分（必须是0到1之间的小数，如0.85）。
    * `development_stage`: 必须从以下四个选项中选择一个：["成熟期", "成长期", "探索期", "并购整合期"]。不要使用其他描述。
    * `timeline`: 仅当原文明确提及业务开始时间或近期关键事件时才填充对应字段，否则返回null。
    * `metrics`: 在此字段中，你只能填充在原文中找到的【具体的数值或百分比】。重要说明：
      - 所有数值必须是纯数字，不要包含单位或文字描述
      - 如"150%"应该填写150.0
      - 如"超过60%"应该填写60.0
      - 如"约1.25亿美元"应该填写125000000.0
      - 如果原文只提供了定性描述或带单位的文字描述无法转换为纯数字，则该字段应为null
    * `relations`: 提取在原文中明确提到的主要子公司、参股公司或合作伙伴。
    * `source_sentences`: 必须从原文中摘录2-3句最能支撑你本次提取结论的核心句子。

# JSON输出模板 (必须严格遵守)
{{
  "company_name_full": "...",
  "company_name_short": "...",
  "company_code": "...",
  "exchange": "...",
  "top_shareholders": [
    {{
      "name": "...",
      "holding_percentage": 0.0
    }}
  ],
  "business_concepts": [
    {{
      "concept_name": "...",
      "concept_category": "...",
      "description": "...",
      "importance_score": 0.0,
      "development_stage": "...",
      "timeline": {{
          "established": null,
          "recent_event": null
      }},
      "metrics": {{
          "revenue": null,
          "revenue_growth_rate": null,
          "market_share": null,
          "gross_margin": null,
          "capacity": null,
          "sales_volume": null
      }},
      "relations": {{
          "customers": [],
          "partners": [],
          "subsidiaries_or_investees": []
      }},
      "source_sentences": [
        "...",
        "..."
      ]
    }}
  ]
}}

# 输入信息

* **公司名称**: "{company_name}"
* **文档类型**: "{document_type}"
* **文档内容**:
    \"\"\"
    {document_content}
    \"\"\"
"""

    def get_input_variables(self) -> list[str]:
        """Get required input variables."""
        return ["company_name", "document_type", "document_content"]
