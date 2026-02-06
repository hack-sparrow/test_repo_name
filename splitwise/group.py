"""Group model for organizing users and expenses."""

import uuid
from dataclasses import dataclass, field

from splitwise.user import User
from splitwise.expense import Expense


@dataclass
class Group:
    """A group of users who share expenses together."""

    name: str
    members: list[User] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def add_member(self, user: User) -> None:
        if user not in self.members:
            self.members.append(user)

    def remove_member(self, user: User) -> None:
        self.members.remove(user)

    def add_expense(self, expense: Expense) -> None:
        expense.group_id = self.id
        self.expenses.append(expense)

    def get_member_ids(self) -> set[str]:
        return {m.id for m in self.members}
