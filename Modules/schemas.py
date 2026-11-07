"""
Modules/schemas.py

Pydantic models shared by the agents. A model describes the exact shape an
agent must return, and rejects anything else. Day 1 only needs SQLAnswer;
later days add the plan, the KPI and the chart specification here.

SQLAnswer is what the SQL generator returns instead of a bare query:
    status      ok          a query answers the question
                ambiguous   a query is given, but the question had a vague
                            word: the choice is written in `assumptions`
                unsupported the data needed does not exist     (no query)
                blocked     the request asks to change data    (no query)
    sql         the query (only for ok / ambiguous)
    assumptions short sentences the user should see under the panel
    reason      why nothing was produced (for unsupported / blocked)
"""
import json
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["ok", "ambiguous", "unsupported", "blocked"]


class SQLAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")   # unknown fields are an error

    status: Status = "ok"
    sql: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _consistent(self):
        has_sql = bool(self.sql and self.sql.strip())
        if self.status in ("ok", "ambiguous"):
            if not has_sql:
                raise ValueError(f"status '{self.status}' needs a non-empty sql")
            if self.status == "ambiguous" and not self.assumptions:
                raise ValueError("status 'ambiguous' needs at least one assumption")
        else:  # unsupported / blocked
            if has_sql:
                raise ValueError(f"status '{self.status}' must not contain sql")
            if not (self.reason and self.reason.strip()):
                raise ValueError(f"status '{self.status}' needs a reason")
        return self


def parse_sql_answer(text: str) -> SQLAnswer:
    """Turn the model's text into a SQLAnswer.

    Accepts a bare JSON object or one wrapped in a code fence or in extra
    words. Raises ValueError when no valid answer can be read, so that the
    caller can retry or fall back."""
    if not text or not text.strip():
        raise ValueError("The model returned an empty answer.")
    cleaned = re.sub(r"```(?:json|JSON)?", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in the model's answer.")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"The answer is not valid JSON: {e}")
    try:
        return SQLAnswer(**data)
    except Exception as e:  # pydantic.ValidationError
        raise ValueError(f"The answer does not match the expected shape: {e}")
