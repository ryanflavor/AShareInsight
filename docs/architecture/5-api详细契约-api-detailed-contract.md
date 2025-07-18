# **5. API详细契约 (API Detailed Contract)**

  * **Endpoint**: `POST /api/v1/find_related_companies`
  * **描述**: 根据输入的核心公司，检索并返回业务概念上相关的其他上市公司列表。
  * **请求体**:
      * `query_identifier` (string, **required**): 要查询的公司简称或股票代码。
      * `top_k` (integer, optional, default: 20): 希望返回的公司数量上限。
      * `market_filters` (object, optional): 行情数据过滤器。
          * `max_market_cap_cny` (integer, optional): 最大市值 (人民币)。
          * `min_5day_avg_volume` (integer, optional): 最小5日平均成交额。
  * **成功响应 (200 OK)**:
      * `query_company` (object): 查询的核心公司信息 (`name`, `code`)。
      * `results` (array of objects): 相关公司列表，按`relevance_score`降序排列。
          * `company_name` (string)
          * `company_code` (string)
          * `relevance_score` (float)
          * `matched_concepts` (array of objects): 匹配到的核心业务概念列表。
          * `justification` (object):
              * `summary` (string): 自动生成的简明匹配理由。
              * `supporting_evidence` (array of strings): 来自原文的溯源句子。

-----
