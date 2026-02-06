"""Expense model with multiple split strategies."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from splitwise.user import User


class SplitType(Enum):
    EQUAL = "equal"
    EXACT = "exact"
    PERCENTAGE = "percentage"
    SHARES = "shares"


@dataclass
class Expense:
    """A single expense with configurable split logic.

    Attributes:
        description: What the expense is for.
        total_amount: The total cost.
        paid_by: Mapping of User -> amount they paid.
        split_type: How to divide the expense among participants.
        split_data: Depends on split_type:
            - EQUAL: dict of {User: None} (keys are participants, values ignored)
            - EXACT: dict of {User: Decimal amount}
            - PERCENTAGE: dict of {User: percentage as float 0-100}
            - SHARES: dict of {User: number of shares}
        group_id: Optional group this expense belongs to.
    """

    description: str
    total_amount: float
    paid_by: dict[User, float]
    split_type: SplitType
    split_data: dict[User, float | None]
    group_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __post_init__(self) -> None:
        if self.total_amount <= 0:
            raise ValueError("total_amount must be positive")

        paid_total = sum(self.paid_by.values())
        if abs(paid_total - self.total_amount) > 0.01:
            raise ValueError(
                f"Sum of payments ({paid_total}) != total_amount ({self.total_amount})"
            )

        self._validate_split()

    def _validate_split(self) -> None:
        if not self.split_data:
            raise ValueError("split_data must have at least one participant")

        if self.split_type == SplitType.EXACT:
            total = sum(v for v in self.split_data.values() if v is not None)
            if abs(total - self.total_amount) > 0.01:
                raise ValueError(
                    f"Exact split amounts ({total}) must equal total ({self.total_amount})"
                )

        elif self.split_type == SplitType.PERCENTAGE:
            total_pct = sum(v for v in self.split_data.values() if v is not None)
            if abs(total_pct - 100.0) > 0.01:
                raise ValueError(
                    f"Percentages must sum to 100, got {total_pct}"
                )

    def compute_shares(self) -> dict[User, float]:
        """Return how much each participant owes for this expense."""
        if self.split_type == SplitType.EQUAL:
            n = len(self.split_data)
            per_person = self.total_amount / n
            return {user: round(per_person, 2) for user in self.split_data}

        elif self.split_type == SplitType.EXACT:
            return {user: round(amt, 2) for user, amt in self.split_data.items() if amt is not None}

        elif self.split_type == SplitType.PERCENTAGE:
            return {
                user: round(self.total_amount * (pct / 100.0), 2)
                for user, pct in self.split_data.items()
                if pct is not None
            }

        elif self.split_type == SplitType.SHARES:
            total_shares = sum(v for v in self.split_data.values() if v is not None)
            if total_shares == 0:
                raise ValueError("Total shares cannot be zero")
            return {
                user: round(self.total_amount * (shares / total_shares), 2)
                for user, shares in self.split_data.items()
                if shares is not None
            }

        raise ValueError(f"Unknown split type: {self.split_type}")

    def compute_net_balances(self) -> dict[User, float]:
        """Return net balance per user for this expense.

        Positive = user is owed money, Negative = user owes money.
        """
        shares = self.compute_shares()
        all_users = set(self.paid_by.keys()) | set(shares.keys())

        balances: dict[User, float] = {}
        for user in all_users:
            paid = self.paid_by.get(user, 0.0)
            owed = shares.get(user, 0.0)
            balances[user] = round(paid - owed, 2)

        return balances
