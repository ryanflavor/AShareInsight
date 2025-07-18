# **1. 高阶架构 (High Level Architecture)**

## **1.1 技术摘要**

本系统将设计为一个**模块化的、服务导向的架构**。其核心是一个围绕**数据管道**构建的智能引擎，遵循“提取-归档-融合-索引”的流程，最终通过一个独立的API服务层暴露其检索能力。技术栈以Python和LangChain为核心，采用PostgreSQL作为集成的结构化与向量存储方案，并利用本地部署的Qwen模型执行Embedding和Rerank任务，以确保性能和数据私密性。

## **1.2 高阶概述**

  * **架构风格**: 我们将采用**模块化服务架构**。各个核心组件（如数据提取器、融合服务、检索引擎、API接口）将被设计为逻辑上独立、可独立测试的模块。这为未来将某个模块拆分为独立的微服务提供了可能性，但在MVP阶段，它们可以在同一个代码库中开发和部署，以简化运维。
  * **代码仓库结构**: 我们将采用**单体仓库 (Monorepo)** 的方式来管理代码，以便于管理共享代码和未来扩展。
  * **核心数据流**:
    1.  **离线管道 (Offline Pipeline)**: 定期或按需触发，读取原始文档，通过LLM提取结构化数据，经过融合与更新后，存入PostgreSQL主数据库，并同步构建向量索引。
    2.  **在线服务 (Online Service)**: 运行一个独立的API服务，接收用户查询，执行“检索-精排-排序-过滤”的实时计算，并返回最终结果。

## **1.3 高阶项目图**

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

## **1.4 核心架构与开发原则**

1.  **契约驱动开发 (Contract-Driven Development)**: 以Pydantic 2.0模型和API接口定义为“契约”，作为所有模块开发的单一事实来源。
2.  **仓库模式 (Repository Pattern)**: 创建数据访问层，将业务逻辑与数据存储解耦，提高可维护性和可测试性。
3.  **管道模式 (Pipeline Pattern)**: 将离线数据处理流程组织为清晰、模块化的管道，便于调试和扩展。
4.  **依赖注入模式 (Dependency Injection Pattern)**: 在API服务层使用，解耦服务模块，方便单元测试。
5.  **统一日志管理 (Unified Log Management)**: 采用结构化JSON日志，便于调试和维护。
6.  **测试驱动开发 (Test-Driven Development - TDD)**: 使用`pytest`，测试用例基于共享的“契约模型”编写，并通过`pytest-mock`进行依赖隔离。

-----
