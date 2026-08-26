# -*- coding: utf-8 -*-
"""
Polymer AI 多 Agent 复现原型（真实 LLM 版）
==========================================
运行方式:
    python polymer_ai_multiagent_chat.py            # 默认演示（多轮 + 端到端场景）
    python polymer_ai_multiagent_chat.py selftest   # 自检模式（固定问题集）

依赖: pandas, duckdb（标准库另需 csv/statistics/os/urllib）
说明: Intent Agent 真实调用 gpt-4o 端点解析自然语言为结构化 intent JSON；
      Query Skill 用 DuckDB 在内存 DataFrame 上做确定性聚合，结果可复核；
      LLM 只负责"理解与解释"，计算全部由确定性 Skill 完成。
"""
import os, json, csv, statistics
import pandas as pd
import duckdb
import urllib.request

# ============ LLM 配置（真实可用）============
API_KEY = os.getenv("POLYMER_LLM_KEY", "sk-***ttFd")
API_URL = os.getenv("POLYMER_LLM_URL", "https://xiaoai.plus/v1/chat/completions")
MODEL   = os.getenv("POLYMER_LLM_MODEL", "gpt-4o")
CSV_PATH = "polymer_ai_rich_telecom_marketing_dataset.csv"

# 维度（可分组字段）与指标（可度量字段）词汇表，注入给 Intent Agent
DIMENSIONS = ["channel", "strategy_type", "region", "customer_segment", "lifecycle_stage", "week"]
METRICS = ["roi", "conversion_rate", "complaint_rate", "revenue", "conversion",
           "cost", "subsidy_cost", "satisfaction", "reach", "complaint_count", "net_profit"]
RATE_METRICS = {"conversion_rate", "complaint_rate", "satisfaction"}  # 用 AVG 聚合


# ============ LLM 调用 ============
def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


# ============ Agent / Skill 定义 ============
class DataAgent:
    """T1+T2 数据接入与语义建模：规则引擎做 schema profiling（确定性、可离线）。"""
    def profile(self, df: pd.DataFrame):
        schema = []
        n = len(df)
        for col in df.columns:
            series = df[col]
            sample = series.dropna().astype(str).head(3).tolist()
            if pd.api.types.is_numeric_dtype(series):
                role = "metric" if col in METRICS else "numeric"
                stype = "numeric"
            else:
                n_unique = series.nunique()
                if col in DIMENSIONS:
                    role, stype = "dimension", "category"
                elif n_unique <= 12 and col not in ("activity_name",):
                    role, stype = "dimension", "category"
                else:
                    role, stype = "description", "text"
            schema.append({"name": col, "type": stype, "role": role,
                           "unique": int(series.nunique()), "sample": sample})
        return {"fields": schema, "rows": n}


class AutoDashAgent:
    """T3 自动 Dashboard：按字段特征推荐图表（规则）。"""
    def build(self, schema: dict, df: pd.DataFrame):
        dims = [f["name"] for f in schema["fields"] if f["role"] == "dimension"]
        metrics = [f["name"] for f in schema["fields"] if f["role"] == "metric"]
        recs = []
        if "week" in dims and metrics:
            recs.append({"chart": "line", "x": "week", "y": "revenue", "title": "收入趋势（按周）"})
        if "channel" in dims and "roi" in metrics:
            recs.append({"chart": "bar", "x": "channel", "y": "roi", "title": "各渠道 ROI 排名"})
        if "strategy_type" in dims and "roi" in metrics:
            recs.append({"chart": "bar", "x": "strategy_type", "y": "roi", "title": "各策略 ROI 排名"})
        if "risk_level" in dims:
            recs.append({"chart": "pie", "x": "risk_level", "y": "reach", "title": "风险等级分布"})
        return recs


class MemoryAgent:
    """T6 多轮上下文继承：保存上轮结构化 intent。"""
    def __init__(self):
        self.previous_intent = None
    def remember(self, intent: dict):
        self.previous_intent = intent
    def recall(self):
        return self.previous_intent


class IntentAgent:
    """T4 自然语言意图理解：真实调用 gpt-4o 解析为 intent JSON。"""
    SYS = (
        "你是数据分析产品的意图解析器。用户用中文口语提问，你输出严格 JSON，字段：\n"
        "intent_type(aggregate|filter|sort|trend|compare), group_by(维度字段名或null), "
        "metric(指标字段名), filters(数组, 每项{field,op,value}), time_range(如'W1'或null), "
        "sort(asc|desc), chart_type(line|bar|pie|table), confidence(0-1)。\n"
        f"可用维度: {DIMENSIONS}\n可用指标: {METRICS}\n"
        "规则: 只输出指标字段名即可，聚合方式由 Query Skill 统一处理（roi=SUM(revenue)/SUM(cost+subsidy_cost); "
        "conversion_rate=SUM(conversion)/SUM(reach); complaint_rate=SUM(complaint_count)/SUM(reach); satisfaction 用 AVG；其余 SUM）。\n"
        "'划算/性价比'映射为 roi; '转化'映射为 conversion_rate; '投诉'映射为 complaint_rate; "
        "'哪个最高/最低' 设 sort=desc/asc 且 group_by 为对比维度; "
        "上下文追问(如'那投诉风险呢''换成策略维度')需结合上一轮 group_by/metric 改写。\n"
        "只输出 JSON，不要解释。"
    )
    def parse(self, question: str, schema: dict, previous_intent: dict | None) -> dict:
        ctx = f"上一轮意图: {json.dumps(previous_intent, ensure_ascii=False)}" if previous_intent else "首轮（无历史）。"
        fields = ", ".join(f"{f['name']}({f['role']})" for f in schema["fields"])
        user = f"数据模型字段: {fields}\n{ctx}\n用户问题: {question}"
        raw = call_llm(self.SYS, user)
        # 容错：去 code fence
        raw = raw.strip().strip("`").replace("json", "", 1).strip()
        start, end = raw.find("{"), raw.rfind("}")
        intent = json.loads(raw[start:end + 1])
        return intent


class QuerySkill:
    """T5 确定性查询与指标计算：DuckDB 在内存 DataFrame 上执行，结果可复核。
    关键：ROI / 转化率 / 投诉率 是比率指标，必须用 'SUM(分子)/SUM(分母)' 聚合，
    绝不能对每行比率直接 SUM/AVG（否则数值失真）。satisfaction 用 AVG，其余用 SUM。"""
    # 比率指标 = 分子聚合 / 分母聚合
    RATIO_DEF = {
        "roi": ("SUM(revenue)", "SUM(cost) + SUM(subsidy_cost)"),
        "conversion_rate": ("SUM(conversion)", "SUM(reach)"),
        "complaint_rate": ("SUM(complaint_count)", "SUM(reach)"),
    }
    AVG_METRICS = {"satisfaction"}

    @staticmethod
    def metric_expr(metric: str) -> str:
        if metric in QuerySkill.RATIO_DEF:
            num, den = QuerySkill.RATIO_DEF[metric]
            return f"({num}) / ({den})"
        if metric in QuerySkill.AVG_METRICS:
            return f"AVG({metric})"
        return f"SUM({metric})"

    def run(self, intent: dict, df: pd.DataFrame) -> pd.DataFrame:
        gb = intent.get("group_by")
        metric = intent.get("metric") or "roi"
        expr = self.metric_expr(metric)
        where = ""
        flts = intent.get("filters") or []
        if flts:
            conds = []
            for f in flts:
                op = f.get("op", "=")
                val = f["value"]
                if isinstance(val, str):
                    conds.append(f"{f['field']} = '{val}'")
                else:
                    conds.append(f"{f['field']} {op} {val}")
            where = " WHERE " + " AND ".join(conds)
        if gb:
            sql = f"SELECT {gb}, {expr} AS {metric} FROM df{where} GROUP BY {gb}"
        else:
            sql = f"SELECT {expr} AS {metric} FROM df{where}"
        sort = intent.get("sort")
        if sort and gb:
            sql += f" ORDER BY {metric} {sort.upper()}"
        return duckdb.sql(sql).df()

    def sql_text(self, intent: dict) -> str:
        """回显可读 SQL（与 run 同源逻辑），用于报告展示。"""
        gb = intent.get("group_by"); metric = intent.get("metric") or "roi"
        expr = self.metric_expr(metric)
        flts = intent.get("filters") or []
        where = ""
        if flts:
            conds = []
            for f in flts:
                op = f.get("op", "="); val = f["value"]
                conds.append(f"{f['field']} = '{val}'" if isinstance(val, str) else f"{f['field']} {op} {val}")
            where = " WHERE " + " AND ".join(conds)
        if gb:
            sql = f"SELECT {gb}, {expr} AS {metric} FROM df{where} GROUP BY {gb}"
        else:
            sql = f"SELECT {expr} AS {metric} FROM df{where}"
        if intent.get("sort") and gb:
            sql += f" ORDER BY {metric} {intent['sort'].upper()}"
        return sql


class InsightAgent:
    """T7 主动洞察与异常检测：统计规则 + LLM 自然语言解释。"""
    def explain(self, result: pd.DataFrame, metric: str, gb: str | None, use_llm: bool = True) -> str:
        if gb and metric in result.columns:
            vals = result[metric].tolist()
            names = result[gb].tolist()
            top_i = vals.index(max(vals)); low_i = vals.index(min(vals))
            card = f"[{gb}] {names[top_i]} 的 {metric} 最高({vals[top_i]:.3f})；{names[low_i]} 最低({vals[low_i]:.3f})。"
            if use_llm:
                try:
                    sys_p = "你是营销分析顾问，用一句中文业务语言解释下面这张洞察卡片，给出可行动建议，不要重复数字。"
                    expl = call_llm(sys_p, card, temperature=0.3)
                    return card + " " + expl.strip().strip('"')
                except Exception:
                    return card
            return card
        return "（无分组维度，跳过洞察）"


class ReportAgent:
    """T8 报告组织与结果交付。"""
    def compose(self, chart_df: pd.DataFrame, insight: str, suggestion: str = "") -> str:
        lines = ["【分析报告】"]
        lines.append(chart_df.to_string(index=False))
        lines.append("洞察: " + insight)
        if suggestion:
            lines.append("建议: " + suggestion)
        return "\n".join(lines)


class Orchestrator:
    """全局编排：上传建模 -> Dashboard；NLQ 多轮；端到端场景。"""
    def __init__(self):
        self.data = DataAgent(); self.autodash = AutoDashAgent()
        self.memory = MemoryAgent(); self.intent = IntentAgent()
        self.query = QuerySkill(); self.insight = InsightAgent(); self.report = ReportAgent()
        self.df = None; self.schema = None

    def upload_flow(self):
        self.df = pd.read_csv(CSV_PATH)
        self.schema = self.data.profile(self.df)
        dash = self.autodash.build(self.schema, self.df)
        return self.schema, dash

    def nlq(self, question: str, use_llm_insight: bool = False) -> dict:
        prev = self.memory.recall()
        intent = self.intent.parse(question, self.schema, prev)
        conf = float(intent.get("confidence", 1.0))
        if conf < 0.60:
            return {"clarification": True, "intent": intent,
                    "message": f"您说的可能指: {intent.get('candidates')}？请确认。"}
        result = self.query.run(intent, self.df)
        gb = intent.get("group_by"); metric = intent.get("metric") or "roi"
        insight = self.insight.explain(result, metric, gb, use_llm=use_llm_insight)
        self.memory.remember(intent)
        return {"intent": intent, "sql": self.query.sql_text(intent),
                "result": result, "insight": insight, "confidence": conf}


# ============ 演示主流程 ============
def banner(t): print("\n" + "=" * 64 + f"\n{t}\n" + "=" * 64)

def main():
    orch = Orchestrator()
    banner("阶段一：数据上传与自动建模")
    schema, dash = orch.upload_flow()
    print(f"数据集: {schema['rows']} 行 × {len(schema['fields'])} 字段")
    print("Schema(前6字段):")
    for f in schema["fields"][:6]:
        print(f"  - {f['name']:18s} type={f['type']:8s} role={f['role']:9s} sample={f['sample']}")
    print("AutoDash 推荐视图:")
    for d in dash:
        print(f"  [{d['chart']}] {d['title']}  (x={d['x']}, y={d['y']})")

    banner("阶段二：多轮自然语言问数（Memory Agent 上下文继承）")
    turns = ["哪个渠道ROI最高？", "那投诉风险呢？", "换成策略维度看ROI", "转化率最高的是谁？"]
    for i, q in enumerate(turns, 1):
        print(f"\n--- Turn {i} | 用户: {q} ---")
        out = orch.nlq(q, use_llm_insight=False)
        if out.get("clarification"):
            print("澄清:", out["message"]); continue
        print("Intent JSON:", json.dumps(out["intent"], ensure_ascii=False))
        print("SQL:", out["sql"])
        print(out["result"].to_string(index=False))
        print("洞察:", out["insight"])

    banner("阶段三：端到端场景（华东最划算？真实 LLM 解析 + 澄清 + 计算 + 解释）")
    q = "哪个渠道在华东最划算？"
    print("用户:", q)
    out = orch.nlq(q, use_llm_insight=True)
    intent = out["intent"]; conf = out["confidence"]
    print(f"置信度={conf} -> ", "中置信度：执行并澄清" if 0.60 <= conf < 0.85 else "直接执行")
    if 0.60 <= conf < 0.85:
        print(f"  澄清追问: 您说的'划算'是指 ROI 吗？(执行 ROI 排名)")
    print("Intent JSON:", json.dumps(intent, ensure_ascii=False))
    print("SQL:", out["sql"])
    print(out["result"].to_string(index=False))
    print("洞察:", out["insight"])
    # 综合效能建议（规则）
    res = out["result"]
    best = res.iloc[0]
    worst_comp = orch.query.run({"group_by": "channel", "metric": "complaint_rate",
                                  "filters": [{"field": "region", "op": "=", "value": "华东"}],
                                  "sort": "desc"}, orch.df)
    suggestion = f"华东地区 {best['channel']} 综合效能最优（ROI={best['roi']:.3f}），建议优先配置资源；" \
                 f"投诉最高渠道为 {worst_comp.iloc[0]['channel']}（投诉率={worst_comp.iloc[0]['complaint_rate']:.4f}），建议复盘话术。"
    print("建议:", suggestion)
    print("\nDONE.")


if __name__ == "__main__":
    main()
