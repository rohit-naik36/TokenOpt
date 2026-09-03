"""Framework-agnostic message types for TokenOpt optimizer.

These use plain dataclasses so the SDK has no soft dependency on Pydantic
or any specific web framework. Host applications convert their own message
representation into these (or pass compatible dicts, see ``PromptOptimizer``).
"""

from dataclasses import dataclass


@dataclass
class Message:
    """A single chat message in the optimization pipeline."""

    role: str
    content: str
    name: str | None = None

    @classmethod
    def from_mapping(cls, mapping) -> "Message":
        """Build a Message from any object exposing role/content (dict or Mapping)."""
        if hasattr(mapping, "get"):
            return cls(
                role=str(mapping.get("role", "user")),
                content=str(mapping.get("content", "")),
                name=mapping.get("name"),
            )
        return cls(
            role=str(getattr(mapping, "role", "user")),
            content=str(getattr(mapping, "content", "")),
            name=getattr(mapping, "name", None),
        )
