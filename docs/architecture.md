# **架构文档: 企业业务概念智能检索系统 (MVP)**

**文档版本**: 1.1 (最终详细版)
**创建日期**: 2025年7月17日
**架构师**: Winston

## **1. 高阶架构 (High Level Architecture)**

### **1.1 技术摘要**

本系统将设计为一个**模块化的、服务导向的架构**。其核心是一个围绕**数据管道**构建的智能引擎，遵循“提取-归档-融合-索引”的流程，最终通过一个独立的API服务层暴露其检索能力。技术栈以Python和LangChain为核心，采用PostgreSQL作为集成的结构化与向量存储方案，并利用本地部署的Qwen模型执行Embedding和Rerank任务，以确保性能和数据私密性。

### **1.2 高阶概述**

  * **架构风格**: 我们将采用**模块化服务架构**。各个核心组件（如数据提取器、融合服务、检索引擎、API接口）将被设计为逻辑上独立、可独立测试的模块。这为未来将某个模块拆分为独立的微服务提供了可能性，但在MVP阶段，它们可以在同一个代码库中开发和部署，以简化运维。
  * **代码仓库结构**: 我们将采用**单体仓库 (Monorepo)** 的方式来管理代码，以便于管理共享代码和未来扩展。
  * **核心数据流**:
    1.  **离线管道 (Offline Pipeline)**: 定期或按需触发，读取原始文档，通过LLM提取结构化数据，经过融合与更新后，存入PostgreSQL主数据库，并同步构建向量索引。
    2.  **在线服务 (Online Service)**: 运行一个独立的API服务，接收用户查询，执行“检索-精排-排序-过滤”的实时计算，并返回最终结果。

### **1.3 高阶项目图**

```mermaid
graph TD
    subgraph "离线数据处理管道 (Offline Data Processing Pipeline)"
        A[原始文档<br/>(年报/研报)] --> B{LLM提取与融合模块<br/>(LangChain Script)};
        B --> C[(PostgreSQL<br/>pgvector)];
    end

    subgraph "在线API服务 (Online API Service)"
        D[用户/客户端] --> E{API服务<br/>(FastAPI)};
        E --> F{检索引擎<br/>(LangChain Chain)};
        F --> C;
    end

    subgraph "外部依赖 (External Dependencies)"
        G[LLM API<br/>(Gemini 2.5 Pro)]
    end

    B --> G;
```

### **1.4 核心架构与开发原则**

1.  **契约驱动开发 (Contract-Driven Development)**: 以Pydantic 2.0模型和API接口定义为“契约”，作为所有模块开发的单一事实来源。
2.  **仓库模式 (Repository Pattern)**: 创建数据访问层，将业务逻辑与数据存储解耦，提高可维护性和可测试性。
3.  **管道模式 (Pipeline Pattern)**: 将离线数据处理流程组织为清晰、模块化的管道，便于调试和扩展。
4.  **依赖注入模式 (Dependency Injection Pattern)**: 在API服务层使用，解耦服务模块，方便单元测试。
5.  **统一日志管理 (Unified Log Management)**: 采用结构化JSON日志，便于调试和维护。
6.  **测试驱动开发 (Test-Driven Development - TDD)**: 使用`pytest`，测试用例基于共享的“契约模型”编写，并通过`pytest-mock`进行依赖隔离。

-----

## **2. 技术栈 (Tech Stack)**

| 类别 | 技术/工具 | **最终确认版本** |
| :--- | :--- | :--- |
| **语言/运行环境** | Python | **3.13** |
| **核心AI框架** | LangChain Core | **\>=0.2.17** |
| **API框架** | FastAPI | **\~0.116.0** |
| **依赖管理** | uv (by Astral) | 最新稳定版 |
| **数据库驱动** | psycopg | **\>=3.1.0 (binary)** |
| **向量存储扩展** | pgvector | **\>=0.2.4** |
| **LangChain DB集成**| **langchain-postgres** | **\>=0.0.12** |
| **数据模型** | Pydantic | **\>=2.0.0** |
| **LLM (提取)** | Gemini 2.5 Pro | `gemini-2.5-pro-preview-06-05` |
| **Embedding模型** | Qwen | 最新版 (本地部署) |
| **Rerank模型** | Qwen | 最新版 (本地部署) |
| **测试框架** | Pytest / pytest-mock | 最新版 |
| **容器化** | Docker / Docker Compose | 最新版 |

-----

## **3. 数据库详细设计**

  * **`companies` (公司主表)**: 存储每个公司的唯一、静态的身份信息。

    | 字段名 | 数据类型 | 约束/索引 | 描述 |
    | :--- | :--- | :--- | :--- |
    | `company_code` | `VARCHAR(10)` | **PRIMARY KEY**, NOT NULL | 公司股票代码，作为唯一主键。 |
    | `company_name_full` | `VARCHAR(255)` | UNIQUE, NOT NULL | 公司完整的官方名称。 |
    | `company_name_short`| `VARCHAR(100)` | INDEX | 公司简称，建立索引以加速查询。 |
    | `exchange` | `VARCHAR(50)` | | 上市交易所。 |
    | `created_at` | `TIMESTAMPTZ` | DEFAULT NOW() | 记录创建时间。 |
    | `updated_at` | `TIMESTAMPTZ` | DEFAULT NOW() | 记录最后更新时间。 |

  * **`source_documents` (原始文档提取归档表)**: 永久、不可变地归档每一次的完整JSON提取结果。

    | 字段名 | 数据类型 | 约束/索引 | 描述 |
    | :--- | :--- | :--- | :--- |
    | `doc_id` | `UUID` | **PRIMARY KEY** | 文档提取记录的唯一ID。 |
    | `company_code` | `VARCHAR(10)` | **FOREIGN KEY** -\> companies.company\_code | 关联到`companies`表。 |
    | `doc_type` | `VARCHAR(50)` | | 文档类型 ("annual\_report", "research\_report")。 |
    | `doc_date` | `DATE` | | 文档的发布日期。 |
    | `report_title` | `TEXT` | | 研报或年报的标题。 |
    | `raw_llm_output` | `JSONB` | NOT NULL | 存储从LLM返回的完整JSON。 |
    | `created_at` | `TIMESTAMPTZ` | DEFAULT NOW() | 记录归档时间。 |

  * **`business_concepts_master` (业务概念主数据表)**: 存储经过融合更新的、每个公司当前最权威的业务概念画像。

    | 字段名 | 数据类型 | 约束/索引 | 描述 |
    | :--- | :--- | :--- | :--- |
    | `concept_id` | `UUID` | **PRIMARY KEY** | 业务概念的唯一ID。 |
    | `company_code` | `VARCHAR(10)` | **FOREIGN KEY** -\> companies.company\_code, INDEX | 关联到`companies`表。 |
    | `concept_name` | `VARCHAR(255)` | NOT NULL, INDEX | 业务概念的通用名称。 |
    | `embedding` | `VECTOR(2560)` | **HNSW INDEX**, NOT NULL | 存储由Qwen Embedding模型生成的向量。 |
    | `concept_details` | `JSONB` | | 存储该概念的所有其他详细信息 (`description`, `category`, `metrics`等)。 |
    | `last_updated_from_doc_id` | `UUID` | FOREIGN KEY -\> source\_documents.doc\_id | 指向`source_documents`表，用于追溯最新信息来源。 |
    | `updated_at` | `TIMESTAMPTZ` | DEFAULT NOW() | 记录该概念的最后更新时间。 |

-----

## **4. 源代码目录结构 (Source Tree)**

```plaintext
/enterprise-concept-retriever/
|
├── .venv/                  # 由uv管理的Python虚拟环境
|
├── packages/               # Monorepo的核心，存放所有独立的模块包
│   │
│   ├── core/               # 【共享核心包】
│   │   └── src/core/
│   │       └── models.py   # Pydantic 2.0 数据模型 ("契约")
│   │
│   ├── pipeline/           # 【离线数据处理管道包】
│   │   └── src/pipeline/
│   │       ├── steps/      # 存放管道的每个独立步骤
│   │       └── main.py     # 运行整个数据管道的主脚本
│   │
│   └── api_server/         # 【在线API服务包】
│       └── src/api_server/
│           ├── routers/    # 定义API的端点
│           ├── services/   # 存放核心业务逻辑
│           └── main.py     # FastAPI应用的启动入口
|
├── tests/                  # 所有测试代码的根目录
|
├── pyproject.toml          # uv管理的项目配置与依赖
└── README.md               # 项目说明文档
```

-----

## **5. API详细契约 (API Detailed Contract)**

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

## **6. 基础设施与部署策略 (私有化部署版)**

  * **环境策略**: 开发（本地Docker）、预发布（内部服务器）、生产（内部服务器）。
  * **CI/CD**: 使用 **GitHub Actions** 进行CI（测试、构建），并通过 **Self-hosted Runner**（部署在内网）将Docker镜像安全地部署到内部服务器。
  * **基础设施**:
      * **应用运行环境**: MVP阶段使用 `Docker Compose` 在目标服务器上部署，未来可扩展至 `Kubernetes (K3s)`。
      * **数据库**: 以Docker容器形式部署的**自建PostgreSQL数据库实例**。
      * **容器镜像仓库**: 在内部搭建私有镜像仓库，如 **Harbor**。

-----

## **7. 错误处理与日志记录策略**

  * **API层**: 使用FastAPI的**全局异常处理器**，将所有内部错误转化为标准化的JSON错误响应（包含`code`, `message`, `request_id`）。
  * **数据管道层**: 采用\*\*“死信队列”\*\*模式，将处理失败的文档隔离，确保管道主体流程的持续运行。
  * **日志记录**: 所有日志以**结构化的JSON格式**输出，并包含丰富的上下文信息。

-----

## **8. 测试策略 (Testing Strategy)**

  * **测试金字塔**: 以大量的**单元测试**为基础，辅以适量的**集成测试**和少量的**端到端测试**。
  * **单元测试**: 使用 `pytest` 和 `pytest-mock`，在隔离环境中测试单个函数/类，必须模拟所有外部依赖。
  * **集成测试**: 连接到运行在Docker中的真实PostgreSQL数据库，测试模块间的内部协作。
  * **端到端测试**: 使用`httpx`库，向部署在预发布环境上的完整应用发送真实API请求，并验证响应是否符合预期，数据源为一套可控的真实初始化数据。

-----

## **9. 编码标准与规范**

  * **代码格式化与检查**: **Black** 和 **Ruff**。
  * **命名规范**: 严格遵守 **PEP 8**。
  * **类型提示与模型**: **必须**使用类型提示，所有数据模型**必须**基于 **Pydantic 2.0** (`from pydantic import BaseModel`) 进行构建。

-----

## **10. 安全策略 (Security Strategy)**

  * **API认证**: MVP阶段采用**API密钥认证** (`X-API-KEY`)。
  * **依赖安全**: 在CI/CD流程中集成 `uv pip audit` 自动扫描漏洞。
  * **数据安全**: 数据库连接使用TLS/SSL加密；所有凭证通过环境变量管理，严禁硬编码。

-----

## **11. 实施优先级**

1.  **Phase 1 (技术验证)**: 搭建最小化原型，验证LangChain最新版本与`langchain-postgres`的兼容性；验证本地Qwen模型的部署与调用。
2.  **Phase 2 (核心流程实现)**: 依据PRD，实现完整的数据提取、存储、索引和基础检索API功能。
3.  **Phase 3 (优化与高级功能)**: 集成Rerank模型，对性能进行调优，并完善监控与运维。