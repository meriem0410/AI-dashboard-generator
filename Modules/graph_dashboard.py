"""
Modules/graph_dashboard.py

The orchestrator: one graph for a whole dashboard request.

    START -> plan -> panels -> assemble -> END

    plan      the planner (Modules/Agents/Agent_dashboard.py): the request
              becomes items, plus unsupported and blocked requests
    panels    each item goes through the panel graph (Modules/graph_panel.py);
              for now one after another (Day 5 runs them in parallel)
    assemble  put the plan, the results and the notices together

Requests the data cannot answer, and requests to change data, are not lost:
they come back in `unsupported` and `blocked` with their reasons, so the
interface can show them.

run_dashboard(question, schema, db, on_progress=None) returns
    {"question", "plan": {"title", "focus", "items": [dict, ...]},
     "results": [{"item", "df", "error", "sql", "attempts", "status",
                  "assumptions", "notes", "stage", "path"}, ...],
     "unsupported": [...], "blocked": [...], "path": [...]}
"""
import operator
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from Modules.Agents.Agent_dashboard import plan_dashboard
from Modules.graph_panel import build_panel_graph, run_panel


class DashboardState(TypedDict, total=False):
    question: str
    schema: str
    plan: Any                          # a Plan
    results: list
    path: Annotated[list, operator.add]
    dashboard: dict


def build_dashboard_graph(db, on_progress=None, max_attempts=3):
    panel_graph = build_panel_graph(db)

    def plan(state):
        return {"plan": plan_dashboard(state["question"], state["schema"]),
                "path": ["plan"]}

    def panels(state):
        items = state["plan"].items
        results = []
        for i, item in enumerate(items):
            if on_progress:
                on_progress(i, len(items), item.title)
            out = run_panel(item.question, state["schema"], db,
                            max_attempts=max_attempts, graph=panel_graph,
                            kind=item.kind, constraints=item.constraints)
            df = out.get("result") if out.get("success") else None
            error = out.get("error")
            if out.get("success") and (df is None or df.empty):
                df, error = None, "The query returned no data."
            results.append({
                "item": {"id": item.id, "title": item.title,
                         "question": item.question, "kind": item.kind},
                "df": df, "error": error if not out.get("success") or df is None else None,
                "sql": out.get("sql"), "attempts": out.get("attempts", 1),
                "status": out.get("status", "ok"),
                "assumptions": out.get("assumptions", []),
                "notes": out.get("notes", []),
                "stage": out.get("stage"), "path": out.get("path"),
            })
        return {"results": results, "path": ["panels"]}

    def assemble(state):
        p = state["plan"]
        return {"dashboard": {
            "question": state["question"],
            "plan": {"title": p.title, "focus": p.focus,
                     "items": [r["item"] for r in state["results"]]},
            "results": state["results"],
            "unsupported": [f.model_dump() for f in p.unsupported],
            "blocked": [f.model_dump() for f in p.blocked],
            "path": list(state.get("path", [])) + ["assemble"],
        }, "path": ["assemble"]}

    graph = StateGraph(DashboardState)
    graph.add_node("plan", plan)
    graph.add_node("panels", panels)
    graph.add_node("assemble", assemble)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "panels")
    graph.add_edge("panels", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()


def run_dashboard(question, schema, db, on_progress=None, max_attempts=3):
    graph = build_dashboard_graph(db, on_progress, max_attempts)
    state = graph.invoke({"question": question, "schema": schema,
                          "results": [], "path": []},
                         config={"recursion_limit": 20})
    return state["dashboard"]
