# 代码交付清单（DELIVERY）

> 供应链协同中台与 RAG Agent 原型 · 完整可运行交付包
> 本文件是交付包的「总说明」，与 `README.md`（运行指南）、`docs/`（业务与架构叙事）配套使用。
---

## 1. 环境与依赖

- **Python 3.10+**（本机验证 3.13.14 通过）。
- **零第三方依赖**：仅用标准库 `csv / json / math / statistics / re / argparse`。
- 生产级升级可选：`chromadb / sentence-transformers / fastapi / pydantic`（见 `requirements.txt` 注释，未强制）。

---

## 2. 目录结构与文件职责

| 路径 | 类型 | 职责 |
|------|------|------|
| `docs/06_RAG_Agent评测与BadCase复盘.md` | 文档 | 完整评测与 Bad Case 复盘（方法论叙事，可进作品集/面试） |
| `README.md` | 文档 | 运行指南 |
| `DELIVERY.md` | 文档 | 交付清单（结构/职责/运行/评测体系/指标/边界/复盘） |
| `data/real_supply_chain.csv` | 数据 | 公开原始数据集（未改动，含来源说明） |
| `data/clean_supply_chain.csv` | 数据 | 清洗后结构化数据（工具层直接消费） |
| `data/eval_cases.json` | 评测 | 21 条评测集（type/grounding/verify/expected） |
| `data/eval_results.json` | 评测 | 评测结果：指标 + 逐条明细（自动生成） |
| `knowledge_base/business_rules.md` | 知识 | 安全库存 / 再订货点 / 应用说明（带出处） |
| `knowledge_base/algorithm_params.md` | 知识 | EOQ / ABC 分类 / 应用说明（带出处） |
| `knowledge_base/sop.md` | 知识 | SOP-1 缺陷率判定 / SOP-2 供应商评分卡 |
| `src/chunker.py` | 代码 | Markdown 切片：按 `##` 标题切 + `section_path` 来源元数据 |
| `src/mcp_tools.py` | 代码 | 7 个真实数据工具 + `tool_manifest()` 能力清单 |
| `src/intent_router.py` | 代码 | 确定性意图路由：`rag / tool / hybrid` |
| `src/rag_agent.py` | 代码 | `LocalRetriever`(TF-IDF 关键词) + 工具派发 + 答案组装 |
| `src/mcp_server.py` | 代码 | MCP 风格 JSON-RPC 服务（tools/list + tools/call） |
| `src/demo.py` | 代码 | 演示入口（真实混合问法） |
| `scripts/clean_data.py` | 代码 | 数据清洗（四舍五入 / 去重改名 / 保留城市维度 + 同义列一致性校验） |
| `tests/eval_rag.py` | 评测 | 21 条真实评测 + **独立参考实现** + 指标计算 |
| `tests/run_tests.py` | 测试 | 统一入口：冒烟测试 + 评测指标校验 |
| `tests/test_rag_agent.py` | 测试 | Agent 冒烟测试（rag/tool/hybrid 三类） |
| `examples/mcp_generate_strategy_request.json` | 示例 | MCP `tools/call` 请求样例 |
| `docs/01~06_*.md` | 文档 | 01项目介绍 / 02需求调研与可行性 / 03中台框架 / 04RAG设计 / 05数据字典 / 06评测与BadCase复盘 |

---

## 3. 如何运行（5 步）

```powershell
# 0)（可选）重新清洗数据；clean_supply_chain.csv 已随包提供
python scripts/clean_data.py

# 1) 演示：跑一条真实混合问法
python src/demo.py
#    Windows 一键：.\run_demo.ps1

# 2) 评测：21 条用例，输出三类指标并写回 eval_results.json
python tests/eval_rag.py

# 3) 测试：冒烟 + 评测校验，全绿即通过
python tests/run_tests.py

# 4) MCP 风格调用（stdin 或 --request-file）
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python src/mcp_server.py
python src/mcp_server.py --request-file examples/mcp_generate_strategy_request.json
```

> MCP 服务支持两种传输：`--request-file` 读单条请求；或 stdin 逐行 JSON-RPC（适合管道/服务化）。

---

## 4. 评测体系（第一性原理）

**三支柱**
1. **采样**：覆盖 `rag(6) / tool(7) / hybrid(8)` 三类，避免只测「会的部分」。
2. **标注**：gold 用「`source > 第N节标题`」语义锚点解析，不用脆弱的位置编号——
   曾因 chunker 把 H1+前言切成 `-1` 导致位置整体错开一位，gold 错位让 Recall 虚假报成 21.4%，修正后真实 92.9%+。
3. **指标正交**：`Recall@3` 只测检索器；`end2end` 测全链路；`intent` 测路由。三者互不替代。

**四层漏斗拆解 bad case**
现象 → 假设（≥2 个候选根因）→ 验证（跑真实中间产物，控制变量）→ 归类（检索/工具/路由/生成/标注）。

**独立参考实现**（防循环论证）
评测对 `tool/hybrid` 的答案用「与 agent 不同代码路径」的参考值校验（如独立 `groupby`/排序），
不直接复用 agent 内部函数结果。

**关键教训**
- 标注优先：标注错了，后续所有 bad case 分析都在错误地基上。
- 中文正则坑：派发用 `"最低\D*(\d+)"` 容忍「最低的5」里的「的」，避免写死字符串漏匹配。
- 同义列先校验再合并：`lead_times_days` 与 `lead_time_days` 看似重复，实则近乎零相关（r≈-0.003），必须分别保留。

---

## 5. 当前评测结果（真实跑出）

| 指标 | 含义 | 值 |
|------|------|-----|
| `end2end_accuracy` | 全部 21 条最终答案正确 | **100.0%**（21/21） |
| `recall_at_3` | rag+hybrid 子集，黄金 chunk 进 top3 | **100.0%**（14/14） |
| `intent_accuracy` | 意图路由分类准确率 | **90.5%**（19/21） |

---

## 6. 已知边界（诚实展示，非缺陷）

两条**意图边界 case** 端到端答案均正确，仅路由标签与评测集标注存在边界分歧：

- **TOOL-01**「SKU0 缺陷率是否超 AQL」：标注为 `tool`，路由判 `hybrid`（问法同时含公式词 AQL）。
- **HY-08**「C 类 SKU 补货管控」：标注为 `hybrid`，路由判 `rag`（「C 类」未被路由的词表识别为具体数据实体）。

二者 e2e 正确，说明「路由标签」与「最终答案正确性」是两个正交维度；若要 100% 路由准确率，
只需在 `intent_router.py` 增加两条词表映射（已在 `docs/` 复盘中说明），但当前选择把它作为
「评测边界 vs 业务正确」的诚实例证保留。

---

## 7. 可扩展路线（生产级）

1. 检索升级：TF-IDF → 向量混合检索 + rerank（注意：先确认是检索缺口还是标注缺口，避免盲目升级）。
2. 路由升级：确定性规则 → LLM 路由，需新建 held-out 评测防过拟合。
3. 工具升级：本地 CSV → 数据库/MCP 真实服务，按 `docs/03` 第 3 节的目标模型差距表补齐订单/仓库实体后，扩展 `replenishment_strategy`（自动补货）等业务语义工具。
4. 评测升级：21 条 → 更大规模 + 自动黄金标注抽检 + 回归门禁（CI 跑 `run_tests.py`）。

---

## 8. 验收清单

- [x] `python src/demo.py` 跑通，输出真实数据结论
- [x] `python tests/eval_rag.py` 指标：e2e 100% / Recall@3 100% / intent 90.5%
- [x] `python tests/run_tests.py` 全绿（ALL TESTS PASSED）
- [x] `python src/mcp_server.py --request-file examples/mcp_generate_strategy_request.json` 返回完整 JSON-RPC 结果
- [x] 数据全真实、无编造；评测指标非预设、由流水线算出
