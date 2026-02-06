"""Main application facade that ties everything together."""

from splitwise.user import User
from splitwise.group import Group
from splitwise.expense import Expense, SplitType
from splitwise.balance import BalanceTracker, Transaction


class SplitwiseApp:
    """Top-level API for the expense splitting application.

    Manages users, groups, expenses, and balances. Users are lightweight
    objects that don't require account creation — just a name.
    """

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._groups: dict[str, Group] = {}
        self._balance_tracker = BalanceTracker()

    # ── User Management ────────────────────────────────────────────

    def add_user(self, name: str, email: str | None = None, phone: str | None = None) -> User:
        user = User(name=name, email=email, phone=phone)
        self._users[user.id] = user
        return user

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def get_all_users(self) -> list[User]:
        return list(self._users.values())

    def remove_user(self, user_id: str) -> User | None:
        return self._users.pop(user_id, None)

    def find_users_by_name(self, name: str) -> list[User]:
        name_lower = name.lower()
        return [u for u in self._users.values() if name_lower in u.name.lower()]

    # ── Group Management ───────────────────────────────────────────

    def create_group(self, name: str, members: list[User] | None = None) -> Group:
        group = Group(name=name, members=list(members) if members else [])
        self._groups[group.id] = group
        return group

    def get_group(self, group_id: str) -> Group | None:
        return self._groups.get(group_id)

    def get_all_groups(self) -> list[Group]:
        return list(self._groups.values())

    def add_user_to_group(self, user_id: str, group_id: str) -> bool:
        user = self._users.get(user_id)
        group = self._groups.get(group_id)
        if user and group:
            group.add_member(user)
            return True
        return False

    def remove_user_from_group(self, user_id: str, group_id: str) -> bool:
        user = self._users.get(user_id)
        group = self._groups.get(group_id)
        if user and group and user in group.members:
            group.remove_member(user)
            return True
        return False

    # ── Expense Management ─────────────────────────────────────────

    def add_expense(
        self,
        description: str,
        total_amount: float,
        paid_by: dict[User, float],
        split_type: SplitType,
        split_data: dict[User, float | None],
        group_id: str | None = None,
    ) -> Expense:
        expense = Expense(
            description=description,
            total_amount=total_amount,
            paid_by=paid_by,
            split_type=split_type,
            split_data=split_data,
            group_id=group_id,
        )

        self._balance_tracker.add_expense(expense)

        if group_id:
            group = self._groups.get(group_id)
            if group:
                group.add_expense(expense)

        return expense

    def add_equal_expense(
        self,
        description: str,
        total_amount: float,
        paid_by_user: User,
        participants: list[User],
        group_id: str | None = None,
    ) -> Expense:
        """Convenience method: one payer, split equally among participants."""
        return self.add_expense(
            description=description,
            total_amount=total_amount,
            paid_by={paid_by_user: total_amount},
            split_type=SplitType.EQUAL,
            split_data={u: None for u in participants},
            group_id=group_id,
        )

    def remove_expense(self, expense_id: str) -> Expense | None:
        return self._balance_tracker.remove_expense(expense_id)

    def get_expenses(self) -> list[Expense]:
        return self._balance_tracker.expenses

    # ── Balance & Settlement ───────────────────────────────────────

    def get_balance(self, user: User) -> float:
        return self._balance_tracker.get_balance(user)

    def get_all_balances(self) -> dict[User, float]:
        return self._balance_tracker.get_all_balances()

    def get_pairwise_balances(self) -> dict[tuple[User, User], float]:
        return self._balance_tracker.get_pairwise_balances()

    def simplify_debts(self) -> list[Transaction]:
        return self._balance_tracker.simplify_debts()

    def settle_debt(self, payer: User, payee: User, amount: float) -> None:
        self._balance_tracker.settle_debt(payer, payee, amount)

    # ── Group-Level Queries ────────────────────────────────────────

    def get_group_balances(self, group_id: str) -> dict[User, float]:
        """Get net balances considering only expenses within a group."""
        group = self._groups.get(group_id)
        if not group:
            return {}

        tracker = BalanceTracker()
        for expense in group.expenses:
            tracker.add_expense(expense)
        return tracker.get_all_balances()

    def simplify_group_debts(self, group_id: str) -> list[Transaction]:
        """Simplify debts for a specific group only."""
        group = self._groups.get(group_id)
        if not group:
            return []

        tracker = BalanceTracker()
        for expense in group.expenses:
            tracker.add_expense(expense)
        return tracker.simplify_debts()
