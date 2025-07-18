# **4. 源代码目录结构 (Source Tree)**

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
