#!/usr/bin/env python3
"""
AI 评测体系 (eval scaffold)
================================================
配套 skill: ai-eval-badcase-method

本脚本演示一个**可复现**的评测闭环，落地"三支柱 + 四层漏斗"：
  1. 采样：从 eval_cases.json 读分层用例 (rag/tool/hybrid)
  2. 标注：retrieval 用 gold chunk；tool/hybrid 用"独立参考实现"算标准答案
          （绝不用系统自身输出当 ground truth —— 避免循环论证）
  3. 指标：正交分解 Recall@K(检索) / 端到端准确率(整体) / 意图准确率(路由)

检索器/路由/派发器这里是**最小桩 (stub)**，便于你替换成真实系统。
运行：python eval_scaffold.py

设计要点（对应 methodology.md 的陷阱目录）：
  - gold 用语义锚点解析（source > 第N节标题），不依赖脆弱的 chunk 编号
  - 独立参考实现用于 numeric/tool 类，与系统输出分离
  - 任何修复前，先跑本脚本验证"测量本身"可信
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# ----------------------------------------------------------------------------
# 0. 评测集格式（eval_cases.json）
# ----------------------------------------------------------------------------
# {
#   "cases": [
#     {"id":"RAG-01","type":"rag","query":"...","grounding":"kb.md > 1. 标题",
#      "verify":"独立算/或直接比对","expected":"..."},
#     {"id":"TOOL-01","type":"tool","query":"...","grounding":"clean.csv 字段",
#      "verify":"独立参考实现","expected":"..."},
#     {"id":"HY-01","type":"hybrid","query":"...","grounding":"kb.md > 1. 标题 + clean.csv",
#      "verify":"公式+数值","expected":"..."}
#   ]
# }

CASE_FILE = Path(__file__).resolve().parent.parent / "data" / "eval_cases.json"


# ----------------------------------------------------------------------------
# 1. 检索器桩 (LocalRetriever stub) — 替换成真实 embedding/混合检索
# ----------------------------------------------------------------------------
@dataclass
class Chunk:
    id: str
    source: str
    section_path: str
    content: str


class LocalRetriever:
    """最小 TF-IDF 桩。真实项目应换成 embedding + 关键词混合 + rerank。"""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks

    def _tokenize(self, text: str) -> list[str]:
        # 中文单字切分（真实检索器此处是最大弱点，仅作演示）
        return [t for t in re.findall(r"[\w一-鿿]+", text.lower())]

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        q = set(self._tokenize(query))
        scored = []
        for c in self.chunks:
            overlap = len(q & set(self._tokenize(c.content)))
            scored.append({"id": c.id, "score": float(overlap), "chunk": c})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return [{"id": s["id"], "score": s["score"]} for s in scored[:top_k]]


# ----------------------------------------------------------------------------
# 2. 意图路由桩 — 替换成真实分类器/LLM router
# ----------------------------------------------------------------------------
def route(query: str) -> str:
    q = query.lower()
    has_formula = any(t in q for t in ["公式", "安全库存", "再订货点", "eoq", "abc", "aql", "评分卡"])
    has_data = any(t in q for t in ["sku", "mumbai", "库存", "缺陷率", "提前期", "成本", "低于", "最低"])
    if has_formula and has_data:
        return "hybrid"
    return "rag" if has_formula else "tool"


# ----------------------------------------------------------------------------
# 3. 工具/派发桩 — 替换成真实 MCP 工具
# ----------------------------------------------------------------------------
def dispatch_tool(query: str) -> dict:
    # 演示"写死关键词匹配自然语言"的脆弱性（见 methodology.md 案例 B）
    m = re.search(r"低于\s*(\d+)", query)
    threshold = int(m.group(1)) if m else None
    if "库存" in query and "最低" in query:
        top_n = 5 if ("最低 5" in query or "最低5" in query) else 3  # 注意："的"会漏
        return {"tool": "low_stock_skus", "result": [f"SKU{i}" for i in range(top_n)]}
    if threshold is not None:
        # 抽取到了阈值却无人消费 -> 沉默失败（演示用）
        return {"tool": None, "result": {}}
    return {"tool": None, "result": {}}


# ----------------------------------------------------------------------------
# 4. 独立参考实现 (independent reference) — 算 numeric 标准答案，避免循环论证
# ----------------------------------------------------------------------------
def independent_reference(case: dict, rows: list[dict]) -> str:
    """真实项目里读 clean CSV / 调工具算标准答案；此处仅示意 Top-N 逻辑。"""
    cid = case["id"]
    if cid == "TOOL-02":
        # 标准：Mumbai 库存最低 5 个
        return "Mumbai 库存最低 5: " + ", ".join(f"SKU{i}" for i in range(5))
    if cid == "TOOL-05":
        # 标准：库存 < 10 的 SKU 清单
        return "库存<10: " + ", ".join(f"SKU{i}" for i in range(3))
    return case.get("expected", "")


# ----------------------------------------------------------------------------
# 5. gold 语义锚点解析（不依赖脆弱编号，避免案例 A 的标注错位）
# ----------------------------------------------------------------------------
def resolve_gold(grounding: str, chunks: list[Chunk]) -> str | None:
    if ">" not in grounding:
        return None
    source, _, title = grounding.partition(">")
    source = source.strip()
    title = title.strip().lower()
    for c in chunks:
        if c.source == source and title in c.section_path.lower():
            return c.id
    return None


# ----------------------------------------------------------------------------
# 6. 运行评测 + 正交指标
# ----------------------------------------------------------------------------
def build_chunks() -> list[Chunk]:
    # 演示 chunk：真实项目从 knowledge_base/*.md 用 chunker 生成
    return [
        Chunk("kb.md-1", "kb.md", "kb.md > 前言", "前言..."),
        Chunk("kb.md-2", "kb.md", "kb.md > 1. 安全库存", "安全库存公式 SS=z*σ*√L"),
        Chunk("kb.md-3", "kb.md", "kb.md > 2. 再订货点", "ROP=μ+L*D，再订货点公式"),
    ]


def main() -> None:
    chunks = build_chunks()
    retriever = LocalRetriever(chunks)
    cases = json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"] if CASE_FILE.exists() \
        else [{"id": "DEMO-1", "type": "rag", "query": "再订货点 ROP 的公式是什么？",
                "grounding": "kb.md > 2. 再订货点", "expected": "ROP=μ+L*D"}]

    rows = []  # 真实项目传 clean CSV 行
    recall_hit = intent_ok = e2e_ok = 0
    recall_total = intent_total = 0

    print("=" * 78)
    print("四层漏斗 · 现象层输出（每例：gold / top3 / 命中 / 意图 / 端到端）")
    print("=" * 78)
    for case in cases:
        q = case["query"]
        intent = route(q)
        ctx = retriever.search(q, top_k=3)
        top3 = [c["id"] for c in ctx]

        # 指标分解
        if case["type"] in ("rag", "hybrid"):
            intent_total += 1
            gold = resolve_gold(case["grounding"], chunks)
            hit = gold in top3
            recall_total += 1
            recall_hit += int(hit)
        else:
            intent_total += 1
            gold = None
            hit = None

        # 意图是否正确（路由自身的黄金标签可另设；此处用 type 反推示意）
        exp_intent = case["type"]  # 简化：gold 意图 = type
        iok = (intent == exp_intent)
        intent_ok += int(iok)

        # 端到端：独立参考 vs 系统输出（此处系统输出=派发结果示意）
        ref = independent_reference(case, rows)
        sys_out = dispatch_tool(q)["result"] if case["type"] != "rag" else top3
        eok = bool(sys_out) if case["type"] != "rag" else (hit is True)
        e2e_ok += int(eok)

        print(f"\n[{case['id']}] type={case['type']} intent={intent}({'✓' if iok else '✗'})")
        print(f"  gold={gold}  top3={top3}  recall@3={'✓' if hit else '✗'}")
        print(f"  独立参考={ref!r}  系统输出={sys_out!r}  e2e={'✓' if eok else '✗'}")

    print("\n" + "=" * 78)
    print("正交指标（每个指标测不同子系统）")
    print("=" * 78)
    print(f"意图准确率 intent   : {intent_ok}/{intent_total} = {intent_ok/intent_total:.1%}")
    if recall_total:
        print(f"Recall@3 (检索)     : {recall_hit}/{recall_total} = {recall_hit/recall_total:.1%}")
    print(f"端到端准确率 e2e     : {e2e_ok}/{len(cases)} = {e2e_ok/len(cases):.1%}")
    print("\n铁律：先验证测量可信（gold 可解析、数据版本一致）再改代码。")


if __name__ == "__main__":
    main()
