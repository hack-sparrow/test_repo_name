"""Balance tracking and debt simplification."""

from collections import defaultdict
from dataclasses import dataclass

from splitwise.user import User
from splitwise.expense import Expense


@dataclass
class Transaction:
    """A simplified debt: `payer` owes `payee` the given `amount`."""

    payer: User
    payee: User
    amount: float

    def __repr__(self) -> str:
        return f"{self.payer.name} -> {self.payee.name}: {self.amount:.2f}"


class BalanceTracker:
    """Tracks net balances across all expenses and simplifies debts.

    The core algorithm:
    1. For each expense, compute how much each user paid vs. how much they owe.
    2. Aggregate net balances per user (positive = owed money, negative = owes money).
    3. Simplify debts using a greedy algorithm that minimizes the number of
       transactions needed to settle all debts.
    """

    def __init__(self) -> None:
        self._expenses: list[Expense] = []
        # net_balances[user] > 0 means user is owed money overall
        self._net_balances: dict[User, float] = defaultdict(float)

    @property
    def expenses(self) -> list[Expense]:
        return list(self._expenses)

    def add_expense(self, expense: Expense) -> None:
        self._expenses.append(expense)
        for user, net in expense.compute_net_balances().items():
            self._net_balances[user] += net

    def remove_expense(self, expense_id: str) -> Expense | None:
        for i, exp in enumerate(self._expenses):
            if exp.id == expense_id:
                removed = self._expenses.pop(i)
                for user, net in removed.compute_net_balances().items():
                    self._net_balances[user] -= net
                return removed
        return None

    def get_balance(self, user: User) -> float:
        """Net balance for a user. Positive = owed money, negative = owes money."""
        return round(self._net_balances.get(user, 0.0), 2)

    def get_all_balances(self) -> dict[User, float]:
        return {u: round(v, 2) for u, v in self._net_balances.items()}

    def get_pairwise_balances(self) -> dict[tuple[User, User], float]:
        """Compute what each user owes every other user across all expenses.

        Returns a dict where key (A, B) with positive value means A owes B that amount.
        Only non-zero pairs are included.
        """
        owes: dict[tuple[User, User], float] = defaultdict(float)

        for expense in self._expenses:
            shares = expense.compute_shares()
            payers = expense.paid_by

            for debtor, owed_amount in shares.items():
                for creditor, paid_amount in payers.items():
                    if debtor == creditor:
                        continue
                    # debtor's share of what creditor paid
                    creditor_fraction = paid_amount / expense.total_amount
                    transfer = owed_amount * creditor_fraction
                    if transfer > 0.005:
                        owes[(debtor, creditor)] += transfer

        # Net out A->B vs B->A
        result: dict[tuple[User, User], float] = {}
        seen: set[tuple[str, str]] = set()
        for (a, b), amount in owes.items():
            key = (min(a.id, b.id), max(a.id, b.id))
            if key in seen:
                continue
            seen.add(key)
            reverse = owes.get((b, a), 0.0)
            net = amount - reverse
            if abs(net) > 0.01:
                if net > 0:
                    result[(a, b)] = round(net, 2)
                else:
                    result[(b, a)] = round(-net, 2)

        return result

    def simplify_debts(self) -> list[Transaction]:
        """Simplify all debts into the minimum number of transactions.

        Uses a greedy approach: repeatedly match the largest creditor
        with the largest debtor, settling the smaller of the two amounts.
        This produces at most N-1 transactions for N users.
        """
        # Build list of (user, net_balance) filtering out zero balances
        creditors: list[tuple[User, float]] = []
        debtors: list[tuple[User, float]] = []

        for user, balance in self._net_balances.items():
            b = round(balance, 2)
            if b > 0.01:
                creditors.append((user, b))
            elif b < -0.01:
                debtors.append((user, -b))  # store as positive amount owed

        # Sort descending by amount
        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)

        transactions: list[Transaction] = []

        while creditors and debtors:
            creditor, credit_amt = creditors.pop(0)
            debtor, debt_amt = debtors.pop(0)

            settle = min(credit_amt, debt_amt)
            settle = round(settle, 2)

            if settle > 0.01:
                transactions.append(Transaction(payer=debtor, payee=creditor, amount=settle))

            remaining_credit = round(credit_amt - settle, 2)
            remaining_debt = round(debt_amt - settle, 2)

            if remaining_credit > 0.01:
                creditors.append((creditor, remaining_credit))
                creditors.sort(key=lambda x: x[1], reverse=True)
            if remaining_debt > 0.01:
                debtors.append((debtor, remaining_debt))
                debtors.sort(key=lambda x: x[1], reverse=True)

        return transactions

    def settle_debt(self, payer: User, payee: User, amount: float) -> None:
        """Record a payment from payer to payee (settling a debt).

        This adjusts balances directly — payer's balance goes up (less in debt),
        payee's balance goes down (less owed).
        """
        if amount <= 0:
            raise ValueError("Settlement amount must be positive")
        self._net_balances[payer] += amount
        self._net_balances[payee] -= amount
