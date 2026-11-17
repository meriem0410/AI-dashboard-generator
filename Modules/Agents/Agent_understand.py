
"""
Modules/Agents/Agent_understand.py

The Data Agent: "understands the data" at upload time.

It is a tool-calling agent, built as a small LangGraph loop:

    START -> llm --(asks for tools, budget left)--> tools -> llm
                 \\--(done, or budget spent)--> finalize -> END

    llm       the model sees the overview of the dataset and may call
              profile_tool, schema_tool or sql_tool (Modules/tools.py)
    tools     run the requested tools, give the results back
    finalize  one last call, WITHOUT tools, asks for the dataset card as
              JSON (Groq cannot combine tool calls and a JSON format in one
              request, so the two steps are separate)

The card (Modules/schemas.py: DatasetCard) holds: a summary, a description
per table, notes on columns, a business glossary and KPI ideas. It is then
CHECKED: anything that names a table or column that does not exist is
dropped. Whatever the model fails to write is completed by the basic card
(statistics only), so the knowledge base always works, even when the model
fails, is offline, or use_llm is False.

understand_dataset(db) returns (card, trace). trace tells what happened:
mode ("llm" or "basic"), tool calls used, tools used, graph path, and why
the model was not used if it was not.
"""

import json
import operator
from typing import Annotated, Optional, TypedDict

from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, StateGraph

from config import GROQ_MODEL, client
from Modules.knowledge_base import build_basic_card, collect_schema_info
from Modules.relationships import describe, detect_relationships
from Modules.schemas import (
    ColumnNote,
    DatasetCard,
    GlossaryEntry,
    KPIIdea,
    TableCard,
    parse_json_model,
)
from Modules.sql_generator import complete_json
from Modules.tools import make_tools


MAX_CALLS = 8
MAX_TOOL_CHARS = 6000
MAX_GLOSSARY = 30
MAX_KPI_IDEAS = 15


SYSTEM_PROMPT = """You are a Data Agent. You study a dataset that you cannot see
directly, using tools, so that another AI can later write correct SQL on it.

Tools: profile_tool(table), schema_tool(table), sql_tool(sql).
You may make at most {max_calls} tool calls in total.

Method
- You are given an overview of every table and the detected relationships.
- Inspect the tables whose purpose or columns are unclear (schema_tool shows
  types, ranges and example values). Use sql_tool only for a small question
  the other tools cannot answer.
- Describe only what the evidence shows. Never guess a column.
- When you have enough evidence, stop calling tools and answer with one short
  sentence."""


FINAL_INSTRUCTION = """Now write the dataset card. Return ONLY one JSON object:
{
  "dataset_summary": "two sentences: what the dataset is about",
  "tables": [{"name": "trips", "description": "one sentence", "entity": "what one row is"}],
  "columns": [{"table": "trips", "column": "trip_status", "description": "one sentence"}],
  "glossary": [{"term": "business word a user may say", "definition": "what it means here",
                "columns": ["table.column"]}],
  "kpi_ideas": [{"name": "short name", "question": "a natural-language question",
                 "columns": ["table.column"]}]
}
Rules: use only the tables and columns that exist; describe every table; add
column notes only where the name alone is ambiguous; give 8 to 12 kpi_ideas
that a manager of this business would want; the glossary maps words users say
(for example "detention", "late") to the columns that define them."""


class UnderstandState(TypedDict, total=False):
    messages: list
    calls: int
    path: Annotated[list, operator.add]
    tools_used: Annotated[list, operator.add]
    draft_text: Optional[str]


def _evidence(messages):
    """The tool results as plain text, for the final call."""

    parts = []
    names = {}

    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls", []) or []:
                names[tc["id"]] = (
                    f'{tc["function"]["name"]}'
                    f'({tc["function"]["arguments"]})'
                )

        elif m.get("role") == "tool":
            parts.append(
                f'{names.get(m["tool_call_id"], "tool")} ->\n{m["content"]}'
            )

    return "\n\n".join(parts) if parts else "(no tool was called)"


def _build_graph(db, tools, overview, relationship_lines, max_calls):
    """Build and compile the Data Agent's LangGraph workflow."""

    by_name = {t.name: t for t in tools}

    # Convert LangChain tools into the OpenAI-compatible format
    # expected by the Groq chat completions API.
    openai_tools = [convert_to_openai_tool(t) for t in tools]

    task = (
        f"DATASET OVERVIEW (from profile_tool):\n{overview}\n\n"
        f"RELATIONSHIPS:\n{relationship_lines or '(none detected)'}\n\n"
        "Inspect what you need, then say you are done."
    )

    # --------------------------------------------------------
    # LLM NODE
    # --------------------------------------------------------

    def llm(state):
        """Ask the model to inspect the dataset or call a tool."""

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=state["messages"],
            tools=openai_tools,
            tool_choice="auto",
            parallel_tool_calls=False,
            temperature=0,
            reasoning_effort="low",
        )

        message = response.choices[0].message

        entry = {
            "role": "assistant",
            "content": message.content or "",
        }

        calls = getattr(message, "tool_calls", None) or []

        if calls:
            entry["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {
                        "name": c.function.name,
                        "arguments": c.function.arguments,
                    },
                }
                for c in calls
            ]

        return {
            "messages": state["messages"] + [entry],
            "path": ["llm"],
        }

    # --------------------------------------------------------
    # CONDITIONAL ROUTING
    # --------------------------------------------------------

    def after_llm(state):
        """Decide whether to execute tools or finalize the card."""

        last = state["messages"][-1]

        if last.get("tool_calls") and state["calls"] < max_calls:
            return "tools"

        return "finalize"

    # --------------------------------------------------------
    # TOOLS NODE
    # --------------------------------------------------------

    def tools_node(state):
        """Execute the tools requested by the model."""

        messages = list(state["messages"])
        calls = state["calls"]
        used = []

        for tc in messages[-1]["tool_calls"]:
            name = tc["function"]["name"]

            if calls >= max_calls:
                result = json.dumps({
                    "ok": False,
                    "error": "tool budget exhausted",
                })

            elif name not in by_name:
                result = json.dumps({
                    "ok": False,
                    "error": f"unknown tool {name}",
                })

            else:
                try:
                    args = json.loads(
                        tc["function"]["arguments"] or "{}"
                    )

                    result = by_name[name].invoke(
                        args if isinstance(args, dict) else {}
                    )

                except Exception as e:
                    result = json.dumps({
                        "ok": False,
                        "error": f"{type(e).__name__}: {e}",
                    })

                calls += 1
                used.append(name)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(result)[:MAX_TOOL_CHARS],
            })

        return {
            "messages": messages,
            "calls": calls,
            "tools_used": used,
            "path": ["tools"],
        }

    # --------------------------------------------------------
    # FINALIZE NODE
    # --------------------------------------------------------

    def finalize(state):
        """Generate the final dataset card without tool calling."""

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(max_calls=max_calls),
            },
            {
                "role": "user",
                "content": (
                    task
                    + "\n\nEVIDENCE GATHERED WITH THE TOOLS:\n"
                    + _evidence(state["messages"])
                    + "\n\n"
                    + FINAL_INSTRUCTION
                ),
            },
        ]

        return {
            "draft_text": complete_json(messages, GROQ_MODEL),
            "path": ["finalize"],
        }

    # --------------------------------------------------------
    # BUILD LANGGRAPH
    # --------------------------------------------------------

    graph = StateGraph(UnderstandState)

    graph.add_node("llm", llm)
    graph.add_node("tools", tools_node)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "llm")

    graph.add_conditional_edges(
        "llm",
        after_llm,
        {
            "tools": "tools",
            "finalize": "finalize",
        },
    )

    graph.add_edge("tools", "llm")
    graph.add_edge("finalize", END)

    initial = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(max_calls=max_calls),
        },
        {
            "role": "user",
            "content": task,
        },
    ]

    return graph.compile(), initial


# ----------------------------------------------------------------------
# CHECKING AND MERGING THE MODEL'S CARD
# ----------------------------------------------------------------------

def merge_card(basic, draft, schema_info):
    """Validate the model's card against the real schema.

    Returns:
        (card, dropped): the merged card and the number of discarded items.
    """

    columns = {
        table: {column["name"] for column in data["columns"]}
        for table, data in schema_info.items()
    }

    dropped = 0

    def valid_ref(ref):
        table, _, column = str(ref).partition(".")
        return table in columns and column in columns[table]

    drafted = {
        table.name: table
        for table in draft.tables
        if table.name in columns
    }

    dropped += len(draft.tables) - len(drafted)

    tables = []

    for table in basic.tables:
        draft_table = drafted.get(table.name)

        tables.append(
            TableCard(
                name=table.name,
                description=(
                    draft_table.description
                    if draft_table and draft_table.description.strip()
                    else table.description
                ),
                entity=(
                    draft_table.entity
                    if draft_table and draft_table.entity.strip()
                    else table.entity
                ),
            )
        )

    notes = [
        note
        for note in draft.columns
        if (
            note.table in columns
            and note.column in columns[note.table]
            and note.description.strip()
        )
    ]

    dropped += len(draft.columns) - len(notes)

    glossary = []

    for entry in draft.glossary:
        if not entry.term.strip() or not entry.definition.strip():
            dropped += 1
            continue

        good = [
            column
            for column in entry.columns
            if valid_ref(column)
        ]

        dropped += len(entry.columns) - len(good)

        glossary.append(
            GlossaryEntry(
                term=entry.term,
                definition=entry.definition,
                columns=good,
            )
        )

    glossary = glossary[:MAX_GLOSSARY]

    ideas = []

    for idea in draft.kpi_ideas:
        good = [
            column
            for column in idea.columns
            if valid_ref(column)
        ]

        dropped += len(idea.columns) - len(good)

        if (
            not idea.name.strip()
            or not idea.question.strip()
            or (idea.columns and not good)
        ):
            dropped += 1
            continue

        ideas.append(
            KPIIdea(
                name=idea.name,
                question=idea.question,
                columns=good,
            )
        )

    # Complete the model's KPI ideas with deterministic template ideas.
    for idea in basic.kpi_ideas:
        if len(ideas) >= MAX_KPI_IDEAS:
            break

        ideas.append(idea)

    card = DatasetCard(
        dataset_summary=(
            draft.dataset_summary.strip()
            or basic.dataset_summary
        ),
        tables=tables,
        columns=notes,
        glossary=glossary,
        kpi_ideas=ideas[:MAX_KPI_IDEAS],
    )

    return card, dropped


def understand_dataset(
    db,
    use_llm=True,
    max_calls=MAX_CALLS,
    relationships=None,
    schema_info=None,
):
    """Return (DatasetCard, trace)."""

    schema_info = schema_info or collect_schema_info(db)

    relationships = (
        detect_relationships(db)
        if relationships is None
        else relationships
    )

    basic = build_basic_card(schema_info)

    trace = {
        "mode": "basic",
        "calls": 0,
        "tools_used": [],
        "path": [],
        "dropped": 0,
        "fallback_reason": None,
    }

    if not use_llm:
        trace["fallback_reason"] = "use_llm is False"
        return basic, trace

    try:
        tools = make_tools(db)

        overview = next(
            tool for tool in tools
            if tool.name == "profile_tool"
        ).invoke({})

        graph, initial = _build_graph(
            db,
            tools,
            overview,
            "\n".join(describe(r) for r in relationships),
            max_calls,
        )

        state = graph.invoke(
            {
                "messages": initial,
                "calls": 0,
                "path": [],
                "tools_used": [],
            },
            config={"recursion_limit": 40},
        )

        trace.update(
            calls=state["calls"],
            tools_used=list(state["tools_used"]),
            path=list(state["path"]),
        )

        draft = parse_json_model(
            state["draft_text"],
            DatasetCard,
        )

    except Exception as e:
        # If the model fails, keep the basic card.
        trace["fallback_reason"] = (
            f"{type(e).__name__}: {str(e)[:200]}"
        )

        return basic, trace

    card, dropped = merge_card(
        basic,
        draft,
        schema_info,
    )

    trace.update(
        mode="llm",
        dropped=dropped,
    )

    return card, trace
