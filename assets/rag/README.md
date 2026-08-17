# 供应链协同中台与 RAG Agent 作品集（代码交付包）

面向「制造企业与上下游供应商/承运商协同效率低、数据孤岛严重、业务规则分散」的真实业务场景，
交付一套**可运行、可评测、可扩展**的 RAG Agent 原型。
「真实数据集 → 工具层 → 意图路由 → 知识检索 → 端到端评测」这条链路做完整。

## 项目亮点

- **真实数据**：基于公开供应链数据集（100 行 × 24 列），经 `scripts/clean_data.py` 规范化，数值全部来自真实样本，非编造。
- **架构分工清晰**：RAG 管知识（SOP/公式），MCP 风格工具管实时数值/统计，意图路由（确定性）决定走哪条路。
- **可评测**：21 条人工标注评测集 + 独立参考实现，跑出真实指标（见下）。
- **诚实复盘**：评测体系本身是第一性原理设计的（采样/标注/指标正交），并把发现的 bad case 修复过程沉淀进 `docs/` 与 skill。

## 目录结构

```text
supply-chain-rag-portfolio/
  README.md                # 本文件
  DELIVERY.md              # 交付清单（结构/职责/运行/评测体系/指标/边界/复盘）
  requirements.txt         # 仅用 Python 标准库，零外部依赖
  run_demo.ps1             # Windows 一键演示
  data/
    real_supply_chain.csv  # 原始公开数据集（未改动）
    clean_supply_chain.csv # 清洗后工具层消费的结构化数据
    eval_cases.json        # 21 条评测集（含 grounding/type/expected）
    eval_results.json      # 评测结果（指标 + 逐条明细）
  knowledge_base/          # RAG 本地知识库（带出处 SOP/公式）
    business_rules.md      # 安全库存 / 再订货点 / 应用说明
    algorithm_params.md    # EOQ / ABC 分类 / 应用说明
    sop.md                 # SOP-1 缺陷率判定 / SOP-2 供应商评分卡
  src/
    chunker.py             # Markdown 切片（按标题切 + section_path 元数据）
    mcp_tools.py           # 7 个真实数据工具 + tool_manifest
    intent_router.py       # 确定性意图路由（rag/tool/hybrid）
    rag_agent.py           # LocalRetriever(TF-IDF) + 工具派发 + 答案组装
    mcp_server.py          # MCP 风格 JSON-RPC 服务（tools/list + tools/call）
    demo.py                # 演示入口
  scripts/
    clean_data.py          # 数据清洗（四舍五入/去重改名/保留城市维度）
  tests/
    eval_rag.py            # 21 条真实评测 + 独立参考实现 + 指标计算
    run_tests.py           # 统一测试入口（冒烟 + 评测校验）
    test_rag_agent.py      # Agent 冒烟测试
  examples/
    mcp_generate_strategy_request.json  # MCP 调用示例请求
  docs/                    # 业务/架构/作品集叙事文档
```

## 环境要求

- Python 3.10+（仅用标准库：`csv / json / math / statistics / re / argparse`）。
- 无需 `pip install` 任何依赖。升级为生产级 RAG 时可加 `chromadb / sentence-transformers / fastapi`（见 requirements.txt 注释）。

## 运行（5 步）

```powershell
# 0) 数据清洗（可选；clean_supply_chain.csv 已随包提供）
python scripts/clean_data.py

# 1) 演示：跑一条真实混合问法
python src/demo.py
#   Windows 一键：.\run_demo.ps1

# 2) 评测：21 条用例，输出三类真实指标并写回 eval_results.json
python tests/eval_rag.py

# 3) 测试：冒烟 + 评测校验，全绿即通过
python tests/run_tests.py

# 4) MCP 风格调用示例
python src/mcp_server.py --request-file examples/mcp_generate_strategy_request.json
```

## 核心交付物

| 模块 | 文件 | 说明 |
|------|------|------|
| 数据清洗 | `scripts/clean_data.py` | 真实数据规范化（含同义列一致性校验） |
| 工具层 | `src/mcp_tools.py` | 7 个真实数据工具 + 能力清单 |
| 意图路由 | `src/intent_router.py` | 确定性 rag/tool/hybrid 路由 |
| 检索+编排 | `src/rag_agent.py` | TF-IDF 检索 + 工具派发 + 答案组装 |
| 知识切片 | `src/chunker.py` | 标题切分 + 来源路径元数据 |
| 知识库 | `knowledge_base/*.md` | 带出处的 SOP/公式（3 篇） |
| 评测 | `tests/eval_rag.py` + `data/eval_cases.json` | 21 条评测 + 独立参考实现 |
| MCP 服务 | `src/mcp_server.py` | JSON-RPC 风格服务 |

## 评测指标（当前真实结果）

| 指标 | 含义 | 当前值 |
|------|------|--------|
| `end2end_accuracy` | 全部 21 条最终答案正确率 | **100%** |
| `recall_at_3` | rag+hybrid 子集，黄金 chunk 进 top3 | **100%** |
| `intent_accuracy` | 意图路由分类准确率 | **90.5%**（19/21） |

> 已知边界（作为**诚实展示**，非缺陷）：`TOOL-01`（SKU0 缺陷率+AQL，标 tool 但路由判 hybrid）、
> `HY-08`（C 类 SKU 管控，标 hybrid 但路由判 rag）两条意图边界 case 的**端到端答案均正确**，
> 仅路由标签与评测集标注存在边界分歧，已在 `docs/` 复盘中说明。

## 评测体系要点（第一性原理）

1. **三支柱**：采样（覆盖 rag/tool/hybrid 三类）→ 标注（gold 语义锚点，非脆弱位置编号）→ 指标正交（Recall 只测检索、e2e 测全链路、intent 测路由，互不替代）。
2. **四层漏斗拆解 bad case**：现象 → 假设（≥2 个）→ 验证（跑真实中间产物）→ 归类（检索/工具/路由/生成/标注）。
3. **独立参考实现**：评测对 tool/hybrid 的答案用「与 agent 不同代码路径」的参考值校验，避免循环论证。
4. **标注优先**：曾因 gold 位置编号整体错开一位导致 Recall 虚假 21.4%，修正标注后真实值为 92.9%+。标注错了，后续所有分析都在错误地基上。

详见 `docs/04_RAG_Agent_设计说明.md`（架构设计）、`docs/06_RAG_Agent评测与BadCase复盘.md`（本节完整复盘），以及可复用 skill `ai-eval-badcase-method`。

## 文档导航

| 文档 | 内容 |
|---|---|
| `docs/01_项目介绍.md` | 一页纸项目概述 |
| `docs/02_需求调研与技术可行性分析.md` | 需求调研、v1 范围裁剪决策、风险与路线图 |
| `docs/03_数据中台与业务中台流程框架.md` | 目标态架构 + 目标模型→v1真实数据映射 |
| `docs/04_RAG_Agent_设计说明.md` | Agent 架构、7 个真实工具、路由规则、ADR 决策记录 |
| `docs/05_数据字典.md` | v1 真实 24 列字段字典 + 知识库/评测数据字典 |
| `docs/06_RAG_Agent评测与BadCase复盘.md` | 评测体系设计与 5 类 bad case 拆解 |
