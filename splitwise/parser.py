"""Natural language expense parser.

Parses sentences like:
  - "Alice paid 100 for dinner with Bob and Charlie"
  - "Bob paid 50 for coffee split equally with Alice and Charlie"
  - "Alice paid 200 for hotel split Alice 100 Bob 60 Charlie 40"
  - "Alice paid 30 for taxi with Bob 60% Alice 40%"
  - "Alice paid 120 for pizza with Bob and Charlie in shares 2 1 1"

Returns a ParseResult with extracted fields and any follow-up questions
needed to complete the expense.
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class ParseState(Enum):
    COMPLETE = "complete"
    NEEDS_INFO = "needs_info"


@dataclass
class ParseResult:
    """Result of parsing a natural language expense description."""

    state: ParseState
    payer_name: str | None = None
    amount: float | None = None
    description: str | None = None
    participant_names: list[str] = field(default_factory=list)
    split_type: str | None = None  # "equal", "exact", "percentage", "shares"
    split_details: dict[str, float] = field(default_factory=dict)
    questions: list[str] = field(default_factory=list)
    raw_input: str = ""

    @property
    def is_complete(self) -> bool:
        return self.state == ParseState.COMPLETE


def _normalize(text: str) -> str:
    return " ".join(text.strip().split())


def _extract_amount(text: str) -> tuple[float | None, str]:
    """Extract a monetary amount from the text and return (amount, remaining_text)."""
    patterns = [
        r'\$\s*([\d,]+(?:\.\d{1,2})?)',
        r'([\d,]+(?:\.\d{1,2})?)\s*(?:dollars|bucks|usd)',
        r'(?:paid|spent|cost|was)\s+\$?([\d,]+(?:\.\d{1,2})?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(",", "")
            remaining = text[:match.start()] + text[match.end():]
            return float(amount_str), _normalize(remaining)

    # Fallback: find any standalone number that looks like money
    match = re.search(r'(?<!\w)([\d,]+(?:\.\d{1,2})?)(?!\w*%)', text)
    if match:
        amount_str = match.group(1).replace(",", "")
        val = float(amount_str)
        if val > 0:
            remaining = text[:match.start()] + text[match.end():]
            return val, _normalize(remaining)

    return None, text


def _extract_payer(text: str, known_names: list[str]) -> tuple[str | None, str]:
    """Extract who paid from the text."""
    # Try "X paid" pattern
    match = re.search(r'(\w+(?:\s+\w+)?)\s+paid', text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        remaining = text[:match.start()] + text[match.end():]
        return name, _normalize(remaining)

    # Try "paid by X" pattern
    match = re.search(r'paid\s+by\s+(\w+(?:\s+\w+)?)', text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        remaining = text[:match.start()] + text[match.end():]
        return name, _normalize(remaining)

    # Try matching known names at the start
    for name in sorted(known_names, key=len, reverse=True):
        if text.lower().startswith(name.lower()):
            remaining = text[len(name):]
            return name, _normalize(remaining)

    return None, text


def _extract_description(text: str) -> tuple[str | None, str]:
    """Extract expense description (what it's for)."""
    match = re.search(r'for\s+(.+?)(?:\s+(?:with|split|between|among|equally)|$)', text, re.IGNORECASE)
    if match:
        desc = match.group(1).strip()
        # Clean up trailing words that aren't part of description
        desc = re.sub(r'\s+(?:split|with|between|among|equally)\s*$', '', desc, flags=re.IGNORECASE)
        if desc:
            remaining = text[:match.start()] + text[match.end():]
            return desc, _normalize(remaining)

    # Try "on X" pattern
    match = re.search(r'on\s+(.+?)(?:\s+(?:with|split|between|among)|$)', text, re.IGNORECASE)
    if match:
        desc = match.group(1).strip()
        if desc:
            remaining = text[:match.start()] + text[match.end():]
            return desc, _normalize(remaining)

    return None, text


def _extract_participants(text: str, known_names: list[str]) -> list[str]:
    """Extract participant names from the text."""
    participants = []

    # Look for "with X, Y, and Z" or "with X and Y" or "between X, Y, Z"
    pattern = r'(?:with|between|among|split\s+(?:equally\s+)?(?:with|between|among)?)\s+(.+)'
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        search_text = match.group(1)
    else:
        # No explicit participant keyword — only match known names from full text
        if known_names:
            lower_text = text.lower()
            for name in sorted(known_names, key=len, reverse=True):
                if name.lower() in lower_text:
                    participants.append(name)
                    lower_text = lower_text.replace(name.lower(), "", 1)
        return participants

    # Try to match known names first
    lower_search = search_text.lower()
    for name in sorted(known_names, key=len, reverse=True):
        if name.lower() in lower_search:
            participants.append(name)
            lower_search = lower_search.replace(name.lower(), "", 1)

    if participants:
        return participants

    # Fall back to splitting by common delimiters
    search_text = re.sub(r'\b(?:and|,|&)\b', '|', search_text, flags=re.IGNORECASE)
    parts = [p.strip() for p in search_text.split('|') if p.strip()]

    for part in parts:
        # Filter out non-name tokens
        cleaned = re.sub(r'[\d$%.]', '', part).strip()
        if cleaned and len(cleaned) > 1 and not cleaned.lower() in ('for', 'the', 'a', 'an', 'split', 'equally', 'in', 'shares'):
            participants.append(cleaned)

    return participants


def _extract_split_details(text: str, participants: list[str]) -> tuple[str | None, dict[str, float]]:
    """Try to extract split type and per-person details."""
    lower = text.lower()

    # Check for "equally" keyword
    if 'equally' in lower or 'equal' in lower:
        return "equal", {}

    # Check for percentage splits: "Alice 60% Bob 40%"
    pct_matches = re.findall(r'(\w+)\s+([\d.]+)\s*%', text, re.IGNORECASE)
    if pct_matches:
        details = {}
        for name, pct in pct_matches:
            details[name] = float(pct)
        if abs(sum(details.values()) - 100.0) < 0.1:
            return "percentage", details

    # Check for exact amounts: "Alice 100 Bob 60 Charlie 40"
    exact_matches = re.findall(r'(\w+)\s+\$?([\d,]+(?:\.\d{1,2})?)\b(?!\s*%)', text)
    if len(exact_matches) >= 2:
        details = {}
        for name, amt in exact_matches:
            if name.lower() not in ('paid', 'for', 'split', 'with', 'and', 'the', 'a', 'an'):
                details[name] = float(amt.replace(",", ""))
        if details:
            return "exact", details

    # Check for shares: "in shares 2 1 1" or "shares Alice 2 Bob 1"
    shares_match = re.search(r'(?:in\s+)?shares?\s+([\d\s,]+)', text, re.IGNORECASE)
    if shares_match and participants:
        nums = re.findall(r'(\d+)', shares_match.group(1))
        if len(nums) == len(participants):
            details = {p: float(n) for p, n in zip(participants, nums)}
            return "shares", details

    return None, {}


def parse_expense(text: str, known_names: list[str] | None = None) -> ParseResult:
    """Parse a natural language expense description.

    Args:
        text: The natural language input.
        known_names: List of known user names to help with matching.

    Returns:
        ParseResult with extracted fields and any follow-up questions.
    """
    if not text or not text.strip():
        return ParseResult(
            state=ParseState.NEEDS_INFO,
            questions=["Please describe the expense. For example: 'Alice paid 50 for dinner with Bob and Charlie'"],
            raw_input=text or "",
        )

    known = known_names or []
    original = text
    questions: list[str] = []

    # Extract components
    amount, text_remaining = _extract_amount(text)
    payer, text_remaining = _extract_payer(text, known)
    # Re-extract from original if payer was in the amount region
    if not payer:
        payer, _ = _extract_payer(original, known)
    description, _ = _extract_description(original)
    participants = _extract_participants(original, known)
    split_type, split_details = _extract_split_details(original, participants)

    # Include payer in participants if not already there
    if payer and payer not in participants:
        # Check case-insensitively
        if not any(p.lower() == payer.lower() for p in participants):
            participants.insert(0, payer)

    # Determine what's missing
    if not payer:
        questions.append("Who paid for this expense?")
    if amount is None:
        questions.append("How much was the total amount?")
    if not description:
        questions.append("What was this expense for? (e.g., dinner, groceries, taxi)")
    if len(participants) < 2:
        questions.append("Who should this be split with? (e.g., Bob and Charlie)")

    # Default to equal split if participants found but no explicit split type
    if not split_type and len(participants) >= 2:
        split_type = "equal"

    state = ParseState.COMPLETE if not questions else ParseState.NEEDS_INFO

    return ParseResult(
        state=state,
        payer_name=payer,
        amount=amount,
        description=description,
        participant_names=participants,
        split_type=split_type,
        split_details=split_details,
        questions=questions,
        raw_input=original,
    )


def parse_followup(previous: ParseResult, answer: str, question_index: int,
                    known_names: list[str] | None = None) -> ParseResult:
    """Update a ParseResult with the answer to a follow-up question.

    Args:
        previous: The previous ParseResult to update.
        answer: The user's answer.
        question_index: Which question (0-indexed) this answers.
        known_names: Known user names for matching.

    Returns:
        Updated ParseResult.
    """
    result = ParseResult(
        state=previous.state,
        payer_name=previous.payer_name,
        amount=previous.amount,
        description=previous.description,
        participant_names=list(previous.participant_names),
        split_type=previous.split_type,
        split_details=dict(previous.split_details),
        questions=list(previous.questions),
        raw_input=previous.raw_input,
    )

    known = known_names or []
    question = previous.questions[question_index] if question_index < len(previous.questions) else ""

    if "who paid" in question.lower():
        result.payer_name = answer.strip()
        if result.payer_name and result.payer_name not in result.participant_names:
            if not any(p.lower() == result.payer_name.lower() for p in result.participant_names):
                result.participant_names.insert(0, result.payer_name)

    elif "how much" in question.lower() or "amount" in question.lower():
        amt, _ = _extract_amount(answer)
        if amt is None:
            # Try parsing the raw answer as a number
            try:
                amt = float(answer.strip().replace("$", "").replace(",", ""))
            except ValueError:
                pass
        result.amount = amt

    elif "what was" in question.lower() or "what is" in question.lower():
        result.description = answer.strip()

    elif "split with" in question.lower() or "who should" in question.lower():
        result.participant_names = _extract_participants(answer, known)
        if result.payer_name and result.payer_name not in result.participant_names:
            if not any(p.lower() == result.payer_name.lower() for p in result.participant_names):
                result.participant_names.insert(0, result.payer_name)

    # Re-evaluate completeness
    new_questions: list[str] = []
    if not result.payer_name:
        new_questions.append("Who paid for this expense?")
    if result.amount is None:
        new_questions.append("How much was the total amount?")
    if not result.description:
        new_questions.append("What was this expense for? (e.g., dinner, groceries, taxi)")
    if len(result.participant_names) < 2:
        new_questions.append("Who should this be split with? (e.g., Bob and Charlie)")

    if not result.split_type and len(result.participant_names) >= 2:
        result.split_type = "equal"

    result.questions = new_questions
    result.state = ParseState.COMPLETE if not new_questions else ParseState.NEEDS_INFO

    return result
