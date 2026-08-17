---
name: ai-eval-badcase-method
description: This skill should be used when designing evaluation systems for AI products (RAG / Agent / LLM / 推荐 / 对话系统), constructing test-case sets, analyzing bad cases, or attributing root causes to improve AI system quality. It provides the three-pillar eval framework (sampling / labeling / orthogonal metrics) and the four-layer bad-case funnel (phenomenon → hypothesis → verification → classification), with control-variable attribution and documented pitfall patterns. Trigger when the user wants to "搭建评测体系", "设计测试用例", "跑 eval", "分析 bad case", "归因", "评测指标为什么低", or build an AI product that must be measured honestly.
agent_created: true
---

# AI 评测体系设计与 Bad Case 拆解方法论

## Overview

This skill encodes a first-principles workflow for measuring and improving AI systems. Unlike traditional software, AI outputs are probabilistic and non-enumerable, so correctness can only be *inferred* from objective measurements on a representative sample—never proven from "the code is right". Use this skill to build eval sets that do not inflate metrics, to dissect failures honestly, and to attribute root causes without guesswork.

The methodology has two halves:
- **评测体系三支柱 (Eval system, 3 pillars):** 采样 (what to test) + 标注 (how to judge) + 指标 (what to report, orthogonally decomposed).
- **Bad Case 四层漏斗 (Bad-case funnel, 4 layers):** 现象层 → 假设层 → 验证层 → 归类层.

Load `references/methodology.md` for the full reasoning, worked examples, and pitfall catalog. Use `scripts/eval_scaffold.py` as a starter for a reproducible eval harness.

## When to Use

- Designing an eval set for a RAG / Agent / LLM feature (or any AI product with probabilistic output).
- Reporting metrics and needing to know *which metric measures which subsystem*.
- A metric looks suspiciously low (or high)—before changing code, validate the measurement.
- Running a post-launch bad-case review or building a continuous eval loop.

## Core Principles (load if needed from references/methodology.md)

### 1. Three pillars of an eval system

A working eval = **采样 + 标注 + 指标**. Missing any pillar invalidates the result.

- **采样 (what to test):** Enumerate real intent/query-type distribution; stratified-sample cases covering happy / edge / adversarial. Only easy cases → inflated Recall. The eval set must mirror how the system is actually used, including its differentiated value (e.g. hybrid "formula-on-real-data" queries).
- **标注 (how to judge / ground truth):** For retrieval, label `gold chunk id`; for tool/numeric, compute the answer with an **independent reference implementation** (never the system's own output—circular proof); for hybrid, both. Attach a `rubric` (e.g. "numeric error <1% counts as correct").
- **指标 (what to report, must be orthogonal):** Decompose so each metric tests a different subsystem. Typical orthogonal set: `Recall@K` (retriever only, rag+hybrid subset) · `端到端准确率` (whole pipeline, all cases) · `意图准确率` (router only). **Never mix them**—mixing hides where the failure lives.

### 2. Four-layer bad-case funnel

Do NOT jump to "it's an X bug" and edit code. Walk all four layers.

1. **现象层 (phenomenon):** Open the eval results; read `recall@K / e2e / intent_ok` columns; locate which line broke. State the gold chunk vs actual top-K. No diagnosis yet.
2. **假设层 (hypothesis):** List **≥2 candidate root causes** per case. Keep them as hypotheses, not conclusions.
3. **验证层 (verification):** Inspect real intermediate artifacts—run the retriever's scores, print chunk id↔section, trace the router's output, trace the dispatcher's arguments. **Use evidence to falsify hypotheses; never rely on intuition.**
4. **归类层 (classification):** Map the verified cause onto the root-cause tree (below). Write it into the iteration backlog.

### 3. Root-cause attribution tree (control variable)

Anchor: feed the same input and walk downstream layer-by-layer; the layer whose output is wrong is the root-cause layer. Classify by subsystem:

- **检索根因 (retrieval):** retriever failed to surface the correct chunk (low recall / bad chunking / weak embedding).
- **工具根因 (tool):** numeric computed wrong / wrong field / wrong row-count or口径 (silent failure is most dangerous).
- **路由根因 (router):** intent misclassified → wrong module dispatched.
- **生成根因 (generation):** retrieval+tool both correct, but LLM/prompt/format wrong.
- **标注根因 (labeling):** gold itself is ambiguous or mis-mapped. **Most overlooked, can flip the whole eval.**

### 4. Iron rules

- A metric's credibility is **never higher than its labeling's credibility**.
- Verify before fixing. Running the real scorer once beats ten guesses.
- Distinguish subsystems: tokenizers serve the **retriever**; dispatchers use **string/regex matching**—mixing them up in an interview reveals shallow understanding.
- Prefer "silent failures" detection: code that returns 3 rows instead of 5 (looks fine) is only caught by an independent reference implementation.

## Workflow

1. Define the query-type distribution; stratified-sample N cases (happy/edge/adversarial). Record `type / grounding / verify / expected` per case (see scaffold).
2. Implement an **independent reference** for tool/numeric answers; label `gold chunk id` for retrieval cases.
3. Run the harness; report orthogonal metrics separately.
4. For every failing case, run the four-layer funnel. Always start at 现象层 from the results file.
5. Before any code fix, re-verify the **measurement itself** (gold mapping, recall counting, data version). A wrong baseline wastes the whole iteration.
6. Fix by root-cause class; re-run; report before/after per metric.

## Resources

- `references/methodology.md` — full first-principles derivation, the worked RAG-Agent example (gold-misalignment that faked Recall 21.4%→true 92.9%, and the TOOL-02/05 dispatch bugs), and the pitfall catalog.
- `scripts/eval_scaffold.py` — runnable starter: loads a `eval_cases.json`, computes an independent reference, runs a retriever+router+dispatcher stub, and prints orthogonal metrics + per-case detail. Adapt the stubs to the real system.
