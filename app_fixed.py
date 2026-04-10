from functools import wraps
import io
import random

import pyodbc
from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for
from reportlab.pdfgen import canvas
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"


def get_connection():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost;"
        "DATABASE=BankDB;"
        "Trusted_Connection=yes;"
    )


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        IF OBJECT_ID('accounts', 'U') IS NULL
        BEGIN
            CREATE TABLE accounts (
                id INT IDENTITY(1,1) PRIMARY KEY,
                account_no VARCHAR(20) NOT NULL,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                balance FLOAT NOT NULL DEFAULT 0
            )
        END
        """
    )

    cursor.execute(
        """
        IF OBJECT_ID('transactions', 'U') IS NULL
        BEGIN
            CREATE TABLE transactions (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_id INT NOT NULL,
                transaction_type VARCHAR(20) NOT NULL,
                amount FLOAT NOT NULL,
                transaction_date DATETIME NOT NULL DEFAULT GETDATE(),
                CONSTRAINT FK_transactions_accounts
                    FOREIGN KEY (user_id) REFERENCES accounts(id)
            )
        END
        """
    )

    conn.commit()
    conn.close()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def get_positive_amount(raw_value):
    try:
        amount = float(raw_value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


@app.route("/")
def home():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password_value = request.form.get("password", "")
    balance = get_positive_amount(request.form.get("balance"))

    if not name or not email or not password_value or balance is None:
        flash("Please enter valid account details.")
        return redirect(url_for("home"))

    password = generate_password_hash(password_value)
    acc_no = str(random.randint(1000000000, 9999999999))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM accounts WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        flash("An account with this email already exists.")
        return redirect(url_for("login"))

    cursor.execute(
        "INSERT INTO accounts (account_no, name, email, password, balance) VALUES (?, ?, ?, ?, ?)",
        (acc_no, name, email, password, balance),
    )

    conn.commit()
    conn.close()

    flash("Account created successfully. Please login.")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[4], password):
            session["user_id"] = user[0]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM accounts WHERE id = ?", (session["user_id"],))
    account = cursor.fetchone()

    if not account:
        conn.close()
        session.clear()
        flash("Your session expired. Please login again.")
        return redirect(url_for("login"))

    cursor.execute(
        """
        SELECT transaction_type, amount, transaction_date
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],),
    )
    transactions = cursor.fetchall()
    conn.close()

    insight = "Good savings habit"
    if account[5] >= 10000:
        insight = "Strong balance maintained"

    return render_template(
        "dashboard.html",
        account=account,
        transactions=transactions,
        insight=insight,
    )


@app.route("/deposit", methods=["POST"])
@login_required
def deposit():
    amount = get_positive_amount(request.form.get("amount"))
    if amount is None:
        flash("Please enter a valid deposit amount.")
        return redirect(url_for("dashboard"))

    user_id = session["user_id"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (amount, user_id))
    cursor.execute(
        "INSERT INTO transactions (user_id, transaction_type, amount) VALUES (?, ?, ?)",
        (user_id, "Deposit", amount),
    )

    conn.commit()
    conn.close()

    flash("Deposit successful.")
    return redirect(url_for("dashboard"))


@app.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    amount = get_positive_amount(request.form.get("amount"))
    if amount is None:
        flash("Please enter a valid withdrawal amount.")
        return redirect(url_for("dashboard"))

    user_id = session["user_id"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT balance FROM accounts WHERE id = ?", (user_id,))
    balance_row = cursor.fetchone()

    if not balance_row:
        conn.close()
        session.clear()
        flash("Account not found. Please login again.")
        return redirect(url_for("login"))

    if balance_row[0] < amount:
        conn.close()
        flash("Insufficient balance.")
        return redirect(url_for("dashboard"))

    cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (amount, user_id))
    cursor.execute(
        "INSERT INTO transactions (user_id, transaction_type, amount) VALUES (?, ?, ?)",
        (user_id, "Withdraw", amount),
    )

    conn.commit()
    conn.close()

    flash("Withdrawal successful.")
    return redirect(url_for("dashboard"))


@app.route("/download_statement")
@login_required
def download_statement():
    user_id = session["user_id"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT transaction_type, amount, transaction_date
        FROM transactions
        WHERE user_id = ?
        ORDER BY transaction_date DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(220, 800, "Bank Statement")

    y = 760
    for row in rows:
        transaction_date = row[2].strftime("%Y-%m-%d %H:%M")
        pdf.drawString(50, y, f"{row[0]} | Rs.{row[1]:.2f} | {transaction_date}")
        y -= 25
        if y <= 40:
            pdf.showPage()
            y = 800

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="statement.pdf",
        mimetype="application/pdf",
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


init_db()


if __name__ == "__main__":
    app.run(debug=True)
