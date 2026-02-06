"""User model - supports users without accounts."""

import uuid
from dataclasses import dataclass, field


@dataclass
class User:
    """A user in the expense splitting system.

    Users do not need an account. They are simply identified by a name
    and an auto-generated ID. Optionally an email or phone can be stored
    for display/contact purposes, but no authentication is involved.
    """

    name: str
    email: str | None = None
    phone: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return self.id == other.id

    def __repr__(self) -> str:
        return f"User(name={self.name!r}, id={self.id!r})"
