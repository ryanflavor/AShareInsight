# **4. 源代码目录结构 (Source Tree)**

```plaintext
/AShareInsight/
├── .venv/                  # 由uv管理的Python虚拟环境
├── src/
│   ├── domain/                     # 【领域层】核心业务逻辑，不依赖任何框架
│   │   ├── entities/               # 领域实体 (e.g., company.py, business_concept.py)
│   │   └── services/               # 领域服务 (e.g., similarity_calculator.py, data_fusion.py)
│   │
│   ├── application/                # 【应用层】编排领域服务，完成具体用例
│   │   ├── use_cases/              # 应用用例 (e.g., search_similar_companies.py)
│   │   └── ports/                  # 端口接口定义 (e.g., VectorStorePort, LLMServicePort)
│   │
│   ├── infrastructure/             # 【基础设施层】技术实现与外部服务集成
│   │   ├── persistence/            # 持久化适配器
│   │   │   └── postgres/           #   - PostgreSQL仓储实现和pgvector集成
│   │   ├── llm/                    # LLM集成适配器
│   │   │   └── langchain/          #   - LangChain链、提示模板、解析器
│   │   ├── document_processing/    # 文档处理适配器 (e.t., 年报/研报加载器)
│   │   └── monitoring/             # 监控适配器 (e.g., 指标收集, 链路追踪)
│   │
│   ├── interfaces/                 # 【接口层】与外部世界的交互
│   │   ├── api/                    # REST API (FastAPI)
│   │   │   ├── v1/
│   │   │   │   ├── routers/        # API路由定义
│   │   │   │   └── schemas/        # 请求/响应的Pydantic模型 ("契约")
│   │   └── cli/                    # 命令行接口 (用于运行离线管道)
│   │
│   └── shared/                     # 【共享层】跨层组件
│       ├── config/                 # 配置管理
│       └── exceptions/             # 自定义异常
│
├── tests/                          # 测试
│   ├── unit/                       # 单元测试 (隔离测试单个模块)
│   ├── integration/                # 集成测试 (测试模块间的交互)
│   └── e2e/                        # 端到端测试 (通过API测试完整流程)
│
├── scripts/                        # 辅助脚本
│   ├── migration/                  # 数据库迁移脚本
│   └── evaluation/                 # RAG评估脚本
│
├── config/                         # 部署配置文件 (development.yaml, production.yaml)
│
├── pyproject.toml          # uv管理的项目配置与依赖
└── README.md               # 项目说明文档
└── docker/                         # Docker 相关
    ├── Dockerfile
    └── docker-compose.yaml
```
-----
