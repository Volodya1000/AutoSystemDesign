"""Apply one display-language policy to every generation and repair request."""

from infrastructure.llm.models import Message, MessageRole
from shared.artifact_language import ArtifactLanguage


def apply_artifact_language(
    messages: list[Message], language: ArtifactLanguage
) -> list[Message]:
    """Prepend human-text instructions while preserving structural constraints."""
    language_name: str = (
        "Russian" if language is ArtifactLanguage.RUSSIAN else "English"
    )
    policy: Message = Message(
        role=MessageRole.SYSTEM,
        content=(
            f"Write all human-readable artifact text in {language_name}. "
            "This includes display_name, titles, summaries, role names, "
            "scenario descriptions, conditions, actions and explanations. "
            "Use a concise scenario title (at most 6 words) instead of copying "
            "the entire requirement. Use short action labels (at most 8 words); "
            "put necessary detail in description without restating the action. "
            "Preserve technical identifiers, references, protocol names, JSON "
            "property names, enum values, HTTP methods and URI paths. "
            "Do not translate source evidence or change source-backed claims. "
            "For C4 nodes supply a short human-readable display_name. "
            "These instructions apply equally to initial generation and repair. "
            "Return only the JSON object required by the existing schema."
        ),
    )
    return [policy, *messages]
