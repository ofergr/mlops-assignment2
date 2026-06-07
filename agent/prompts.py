"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

GENERATE_SQL_SYSTEM = """You are a careful text-to-SQL assistant.
Return exactly one SQLite SELECT query and nothing else.
Use only tables and columns shown in the schema.
Quote identifiers with double quotes when they contain spaces, punctuation, or
could be reserved words. Use DISTINCT when a join can repeat the same answer
row. Do not modify data."""

# Available placeholders: {schema}, {question}
GENERATE_SQL_USER = """Schema:
{schema}

Question:
{question}

Write the SQLite query that answers the question."""


VERIFY_SYSTEM = """You are a strict verifier for text-to-SQL results.
Decide whether the SQL execution plausibly answers the user's question.
Return only compact JSON with this shape:
{"ok": true, "issue": ""}

Mark ok=false when the SQL errored, selected irrelevant columns, returned a
place/name/id where the question asks for coordinates or numeric values, ignored
an important filter/aggregation/order in the question, returned duplicate answer
rows where a single distinct list is expected, or returned zero rows when the
question clearly expects existing rows."""

VERIFY_USER = """Question:
{question}

Schema:
{schema}

SQL:
{sql}

Execution result:
{execution}

Does this execution result plausibly answer the question?"""


REVISE_SYSTEM = """You revise failed SQLite queries.
Return exactly one corrected SQLite SELECT query and nothing else.
Use only the provided schema. Preserve useful parts of the previous query, but
fix the verifier's issue."""

REVISE_USER = """Question:
{question}

Schema:
{schema}

Previous SQL:
{sql}

Execution result:
{execution}

Verifier issue:
{issue}

Write a revised SQLite query."""
