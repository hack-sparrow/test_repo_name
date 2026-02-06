"""Tests for the natural language expense parser."""

import pytest

from splitwise.parser import ParseState, parse_expense, parse_followup


class TestBasicParsing:
    def test_full_sentence(self):
        result = parse_expense("Alice paid 50 for dinner with Bob and Charlie")
        assert result.is_complete
        assert result.payer_name == "Alice"
        assert result.amount == 50.0
        assert result.description == "dinner"
        assert "Alice" in result.participant_names
        assert "Bob" in result.participant_names
        assert "Charlie" in result.participant_names

    def test_with_dollar_sign(self):
        result = parse_expense("Bob paid $120 for groceries with Alice")
        assert result.amount == 120.0
        assert result.payer_name == "Bob"
        assert result.description == "groceries"

    def test_split_equally_keyword(self):
        result = parse_expense("Alice paid 100 for hotel split equally with Bob and Charlie")
        assert result.is_complete
        assert result.split_type == "equal"

    def test_known_names_matching(self):
        known = ["Alice Smith", "Bob Jones", "Charlie Brown"]
        result = parse_expense(
            "Alice Smith paid 60 for lunch with Bob Jones and Charlie Brown",
            known_names=known,
        )
        assert result.payer_name == "Alice Smith"
        assert "Bob Jones" in result.participant_names
        assert "Charlie Brown" in result.participant_names

    def test_default_equal_split(self):
        result = parse_expense("Alice paid 100 for dinner with Bob")
        assert result.split_type == "equal"


class TestPercentageParsing:
    def test_percentage_split(self):
        result = parse_expense("Alice paid 100 for taxi with Alice 60% Bob 40%")
        assert result.split_type == "percentage"
        assert result.split_details.get("Alice") == 60.0
        assert result.split_details.get("Bob") == 40.0


class TestExactParsing:
    def test_exact_split(self):
        result = parse_expense(
            "Alice paid 200 for hotel split Alice 100 Bob 60 Charlie 40"
        )
        assert result.split_type == "exact"
        assert result.split_details.get("Alice") == 100.0
        assert result.split_details.get("Bob") == 60.0
        assert result.split_details.get("Charlie") == 40.0


class TestMissingInfo:
    def test_missing_payer(self):
        result = parse_expense("50 for dinner with Bob and Charlie")
        assert not result.is_complete
        assert any("who paid" in q.lower() for q in result.questions)

    def test_missing_amount(self):
        result = parse_expense("Alice paid for dinner with Bob")
        assert not result.is_complete
        assert any("amount" in q.lower() for q in result.questions)

    def test_missing_participants(self):
        result = parse_expense("Alice paid 50 for dinner")
        assert not result.is_complete
        assert any("split with" in q.lower() for q in result.questions)

    def test_empty_input(self):
        result = parse_expense("")
        assert not result.is_complete
        assert len(result.questions) > 0


class TestFollowUp:
    def test_answer_payer(self):
        result = parse_expense("50 for dinner with Bob and Charlie")
        updated = parse_followup(result, "Alice", 0)
        assert updated.payer_name == "Alice"

    def test_answer_amount(self):
        result = parse_expense("Alice paid for dinner with Bob")
        # Find the amount question index
        idx = next(i for i, q in enumerate(result.questions) if "amount" in q.lower())
        updated = parse_followup(result, "75", idx)
        assert updated.amount == 75.0

    def test_answer_amount_with_dollar(self):
        result = parse_expense("Alice paid for dinner with Bob")
        idx = next(i for i, q in enumerate(result.questions) if "amount" in q.lower())
        updated = parse_followup(result, "$120.50", idx)
        assert updated.amount == 120.50

    def test_becomes_complete_after_followup(self):
        result = parse_expense("Alice paid for dinner with Bob")
        assert not result.is_complete
        idx = next(i for i, q in enumerate(result.questions) if "amount" in q.lower())
        updated = parse_followup(result, "50", idx)
        assert updated.is_complete

    def test_answer_participants(self):
        result = parse_expense("Alice paid 50 for dinner")
        idx = next(i for i, q in enumerate(result.questions) if "split" in q.lower())
        updated = parse_followup(result, "Bob and Charlie", idx, known_names=["Bob", "Charlie"])
        assert "Bob" in updated.participant_names
        assert "Charlie" in updated.participant_names
