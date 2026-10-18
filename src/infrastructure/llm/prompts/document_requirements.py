"""Prompts used by the document-requirements extraction adapter."""

SYSTEM_PROMPT: str = (
    "You are a precise software requirements analyst. Return valid JSON only. "
    "Never infer unstated facts or turn assumptions into requirements."
)

USER_PROMPT_TEMPLATE: str = """Extract explicit functional and non-functional requirements from this document fragment.

Rules:
- Extract only claims supported by the source text. Do not invent details.
- Use kind "functional" for system behaviour and "non_functional" for quality attributes, constraints, capacity, latency, availability, security, or similar properties.
- Every requirement must include a short verbatim source_excerpt from this fragment.
- Use source_location only when a heading or location can be identified from the supplied text.
- Report unclear statements in ambiguity_notes and mutually incompatible statements in conflict_notes. Include the conflicting facts; do not resolve them by guessing.
- If the fragment is unrelated to a software system or its requirements, set is_relevant to false and return an empty requirements list.
- Return one JSON object with exactly these keys: requirements, is_relevant, ambiguity_notes, conflict_notes.
- Each requirement must have statement, kind, source_excerpt, and optional source_location.

Source name: {source_name}

<document>
{text}
</document>
"""
