"""All routes for the Splitwise web app."""

import json
from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from splitwise.expense import SplitType
from splitwise.parser import ParseState, parse_expense, parse_followup
from splitwise.web import ADMIN_PASSWORD, ADMIN_USERNAME, splitwise_app

bp = Blueprint(
    "main",
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)


# ── Auth helpers ───────────────────────────────────────────────────


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return decorated


# ── Auth routes ────────────────────────────────────────────────────


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("main.dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


# ── Dashboard ──────────────────────────────────────────────────────


@bp.route("/")
@login_required
def dashboard():
    users = splitwise_app.get_all_users()
    groups = splitwise_app.get_all_groups()
    expenses = splitwise_app.get_expenses()
    balances = splitwise_app.get_all_balances()
    simplified = splitwise_app.simplify_debts()
    return render_template(
        "dashboard.html",
        users=users,
        groups=groups,
        expenses=expenses,
        balances=balances,
        simplified=simplified,
    )


# ── User Management ───────────────────────────────────────────────


@bp.route("/users")
@login_required
def users():
    all_users = splitwise_app.get_all_users()
    balances = splitwise_app.get_all_balances()
    return render_template("users.html", users=all_users, balances=balances)


@bp.route("/users/add", methods=["POST"])
@login_required
def add_user():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip() or None
    phone = request.form.get("phone", "").strip() or None

    if not name:
        flash("Name is required.", "error")
    else:
        user = splitwise_app.add_user(name, email=email, phone=phone)
        flash(f"User '{user.name}' created.", "success")

    return redirect(url_for("main.users"))


@bp.route("/users/<user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    user = splitwise_app.remove_user(user_id)
    if user:
        flash(f"User '{user.name}' removed.", "success")
    else:
        flash("User not found.", "error")
    return redirect(url_for("main.users"))


# ── Group Management ──────────────────────────────────────────────


@bp.route("/groups")
@login_required
def groups():
    all_groups = splitwise_app.get_all_groups()
    all_users = splitwise_app.get_all_users()
    return render_template("groups.html", groups=all_groups, users=all_users)


@bp.route("/groups/add", methods=["POST"])
@login_required
def add_group():
    name = request.form.get("name", "").strip()
    member_ids = request.form.getlist("members")

    if not name:
        flash("Group name is required.", "error")
        return redirect(url_for("main.groups"))

    members = []
    for uid in member_ids:
        user = splitwise_app.get_user(uid)
        if user:
            members.append(user)

    group = splitwise_app.create_group(name, members=members)
    flash(f"Group '{group.name}' created with {len(members)} members.", "success")
    return redirect(url_for("main.groups"))


# ── Add Expense (Natural Language) ─────────────────────────────────


@bp.route("/expense", methods=["GET", "POST"])
@login_required
def add_expense_page():
    all_users = splitwise_app.get_all_users()
    known_names = [u.name for u in all_users]
    groups = splitwise_app.get_all_groups()

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "parse":
            text = request.form.get("text", "")
            result = parse_expense(text, known_names=known_names)

            if result.is_complete:
                return render_template(
                    "add_expense.html",
                    users=all_users,
                    groups=groups,
                    parsed=result,
                    confirm=True,
                )
            else:
                return render_template(
                    "add_expense.html",
                    users=all_users,
                    groups=groups,
                    parsed=result,
                    followup=True,
                )

        elif action == "followup":
            # Reconstruct previous parse result from hidden fields
            prev = _reconstruct_parse_result(request.form)
            answer = request.form.get("answer", "").strip()
            q_index = int(request.form.get("question_index", 0))

            result = parse_followup(prev, answer, q_index, known_names=known_names)

            if result.is_complete:
                return render_template(
                    "add_expense.html",
                    users=all_users,
                    groups=groups,
                    parsed=result,
                    confirm=True,
                )
            else:
                return render_template(
                    "add_expense.html",
                    users=all_users,
                    groups=groups,
                    parsed=result,
                    followup=True,
                )

        elif action == "confirm":
            return _confirm_expense(request.form, known_names)

    return render_template("add_expense.html", users=all_users, groups=groups)


def _reconstruct_parse_result(form):
    """Rebuild a ParseResult from hidden form fields."""
    from splitwise.parser import ParseResult

    questions_json = form.get("questions", "[]")
    participants_json = form.get("participant_names", "[]")
    split_details_json = form.get("split_details", "{}")

    amount_str = form.get("amount", "")
    amount = float(amount_str) if amount_str else None

    return ParseResult(
        state=ParseState.NEEDS_INFO,
        payer_name=form.get("payer_name") or None,
        amount=amount,
        description=form.get("description") or None,
        participant_names=json.loads(participants_json),
        split_type=form.get("split_type") or None,
        split_details=json.loads(split_details_json),
        questions=json.loads(questions_json),
        raw_input=form.get("raw_input", ""),
    )


def _confirm_expense(form, known_names):
    """Create the expense from confirmed parsed data."""
    payer_name = form.get("payer_name", "").strip()
    amount = float(form.get("amount", 0))
    description = form.get("description", "").strip()
    participants_json = form.get("participant_names", "[]")
    participant_names = json.loads(participants_json)
    split_type_str = form.get("split_type", "equal")
    split_details_json = form.get("split_details", "{}")
    split_details = json.loads(split_details_json)
    group_id = form.get("group_id") or None

    # Resolve payer
    payer = _resolve_user(payer_name, known_names)
    if not payer:
        flash(f"Could not find user '{payer_name}'. Please create them first.", "error")
        return redirect(url_for("main.add_expense_page"))

    # Resolve participants
    participants = []
    for name in participant_names:
        user = _resolve_user(name, known_names)
        if user:
            participants.append(user)
        else:
            flash(f"Could not find user '{name}'. Please create them first.", "error")
            return redirect(url_for("main.add_expense_page"))

    if len(participants) < 2:
        flash("Need at least 2 participants.", "error")
        return redirect(url_for("main.add_expense_page"))

    # Build the expense
    split_map = {
        "equal": SplitType.EQUAL,
        "exact": SplitType.EXACT,
        "percentage": SplitType.PERCENTAGE,
        "shares": SplitType.SHARES,
    }
    s_type = split_map.get(split_type_str, SplitType.EQUAL)

    if s_type == SplitType.EQUAL:
        split_data = {u: None for u in participants}
    elif s_type in (SplitType.EXACT, SplitType.PERCENTAGE, SplitType.SHARES):
        split_data = {}
        for user in participants:
            val = split_details.get(user.name)
            if val is None:
                # Fallback: look case-insensitively
                for k, v in split_details.items():
                    if k.lower() == user.name.lower():
                        val = v
                        break
            if val is not None:
                split_data[user] = float(val)
            else:
                flash(f"Missing split value for '{user.name}'.", "error")
                return redirect(url_for("main.add_expense_page"))
    else:
        split_data = {u: None for u in participants}

    try:
        expense = splitwise_app.add_expense(
            description=description,
            total_amount=amount,
            paid_by={payer: amount},
            split_type=s_type,
            split_data=split_data,
            group_id=group_id,
        )
        flash(f"Expense '{expense.description}' (${amount:.2f}) added.", "success")
    except ValueError as e:
        flash(f"Error: {e}", "error")

    return redirect(url_for("main.dashboard"))


def _resolve_user(name, known_names):
    """Find a user by name (case-insensitive)."""
    results = splitwise_app.find_users_by_name(name)
    if results:
        # Prefer exact match
        for u in results:
            if u.name.lower() == name.lower():
                return u
        return results[0]
    return None


# ── History ────────────────────────────────────────────────────────


@bp.route("/history")
@login_required
def history():
    expenses = splitwise_app.get_expenses()
    return render_template("history.html", expenses=expenses)


@bp.route("/expense/<expense_id>/delete", methods=["POST"])
@login_required
def delete_expense(expense_id):
    removed = splitwise_app.remove_expense(expense_id)
    if removed:
        flash(f"Expense '{removed.description}' removed.", "success")
    else:
        flash("Expense not found.", "error")
    return redirect(url_for("main.history"))


# ── Ledger ─────────────────────────────────────────────────────────


@bp.route("/ledger")
@login_required
def ledger():
    balances = splitwise_app.get_all_balances()
    pairwise = splitwise_app.get_pairwise_balances()
    simplified = splitwise_app.simplify_debts()
    return render_template(
        "ledger.html",
        balances=balances,
        pairwise=pairwise,
        simplified=simplified,
    )


# ── Settle ─────────────────────────────────────────────────────────


@bp.route("/settle", methods=["POST"])
@login_required
def settle():
    payer_id = request.form.get("payer_id", "")
    payee_id = request.form.get("payee_id", "")
    amount = float(request.form.get("amount", 0))

    payer = splitwise_app.get_user(payer_id)
    payee = splitwise_app.get_user(payee_id)

    if not payer or not payee:
        flash("Invalid users.", "error")
    elif amount <= 0:
        flash("Amount must be positive.", "error")
    else:
        splitwise_app.settle_debt(payer, payee, amount)
        flash(f"{payer.name} paid {payee.name} ${amount:.2f}.", "success")

    return redirect(url_for("main.ledger"))
