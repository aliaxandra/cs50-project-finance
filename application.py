import os
import time
import re

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # For new user, with no transactions:
    if not db.execute("SELECT * FROM users INNER JOIN transactions ON users.id = transactions.user_id WHERE user_id = :user_id", user_id=session["user_id"]):
        rows = db.execute("SELECT * FROM users WHERE id = :id",
                          id=session["user_id"])

        cash = rows[0]["cash"]
        total_grand = cash

        return render_template("index.html",
                           rows=rows,
                           cash=usd(cash),
                           total_grand=usd(total_grand))

    # Query database
    rows = db.execute(
        "SELECT symbol, SUM(shares), cash FROM transactions INNER JOIN users ON users.id = transactions.user_id WHERE user_id = :user_id GROUP BY symbol",
        user_id=session["user_id"])

    total_grand = 0
    cash = rows[0]["cash"]

    # Call lookup for each stock
    for row in rows:
        if row["SUM(shares)"] > 0:
            quote = lookup(row['symbol'])
            row["name"] = quote["name"]
            row["price_actual"] = usd(quote["price"])
            total_holding = quote["price"] * row["SUM(shares)"]
            row["total_holding"] = usd(total_holding)
            total_grand += total_holding

    total_grand += cash

    return render_template("index.html",
                        rows=rows,
                        cash=usd(cash),
                        total_grand=usd(total_grand)
                        )

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via GET
    if request.method == "GET":
        return render_template("buy.html")

    # User reached route via POST
    else:

        # Error handling

        # Lookup the stock symbol
        quote = lookup(request.form.get("symbol"))

        # If user prints invalid symbol
        if quote == None:
            return apology("invalid symbol", 403)

        # If user prints invalid number of shares
        if int(request.form.get("shares")) <= 0:
            return apology("invalid number of shares", 403)


        # Check if user can afford the stock

        # Calculate overall expence
        expense = quote["price"] * int(request.form.get("shares"))

        # Define user's cash
        rows = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])
        session["cash"] = rows[0]["cash"]

        # If user can't afford the stock
        if expense > session["cash"]:
            return apology("can't afford", 403)


        # If user can afford requested stock, add vlues into  transaction table
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price, transacted) VALUES (:user_id, :symbol, :shares, :price, :transacted)",
            user_id=session["user_id"],
            symbol=request.form.get("symbol").upper(),
            shares=int(request.form.get("shares")),
            price=usd(quote["price"]),
            transacted=time.strftime('%Y-%m-%d %H:%M:%S'))


        # Calculate and update users cash
        cash = session["cash"] - expense

        db.execute("UPDATE users SET cash=? WHERE id=?", cash,
                   session["user_id"])

        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query database
    rows = db.execute(
        "SELECT symbol, shares, price, transacted, cash FROM transactions INNER JOIN users ON users.id = transactions.user_id WHERE user_id = :user_id",
        user_id=session["user_id"])

    return render_template("history.html",
                           rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # Reached via GET display quote form
    if request.method == "GET":
        return render_template("quote.html")

    # By submitting form via POST
    else:

        # Lookup the stock symbol
        quote = lookup(request.form.get("symbol"))

        # If user prints invalid symbol
        if quote == None:
            return apology("invalid symbol", 403)

        else:
            # Get value pairs from JSON
            name = quote["name"]
            symbol = quote["symbol"]
            price = quote["price"]

            return render_template("quoted.html", name=name, symbol=symbol, price=price)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via GET (as by clicking a link or via redirect)
    # Display registration form
    if request.method == "GET":
        return render_template("register.html")

    else:
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username unique
        if len(rows) == 1:
            return apology("the username is already exist", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Check password validation
        passwd = request.form.get("password")

        reg = "^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!#%*?&]{6,20}$"

        # compiling regex
        pat = re.compile(reg)

        # searching regex
        mat = re.search(pat, passwd)

        # validating conditions
        if not mat:
            return apology("password invalid", 403)

        # Ensure password confirmation match the password
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords should mutch", 403)

        # Add new user info into db
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
            username=request.form.get("username"),
            hash=generate_password_hash(request.form.get("password")))

        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Reached via GET display quote form
    if request.method == "GET":

        # Query database
        rows = db.execute(
            "SELECT DISTINCT symbol FROM transactions WHERE user_id = :user_id", user_id=session["user_id"])

        # Define symbols
        for row in rows:
            symbol = row["symbol"]

        return render_template("sell.html", rows=rows)


    # User reached route via POST
    else:

        # Which and how many shares user want to sell
        shares = int(request.form.get("shares"))

        # Query database
        rows = db.execute(
            "SELECT SUM(shares) FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol",
            user_id=session["user_id"],
            symbol=request.form.get("symbol"))

        # Check if user don't have enough shares
        if rows[0]['SUM(shares)'] < shares:
            return apology("not enough shares", 403)


        # If user have enough shares

        # Lookup the stock symbol
        quote = lookup(request.form.get("symbol"))

        income = 0

        # Calculate inncome of the selled shares
        income = quote["price"] * shares

        # Update transaction table
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price, transacted) VALUES (:user_id, :symbol, :shares, :price, :transacted)",
            user_id=session["user_id"],
            symbol=request.form.get("symbol").upper(),
            shares="-"+request.form.get("shares"),
            price=usd(quote["price"]),
            transacted=time.strftime('%Y-%m-%d %H:%M:%S'))


        # Define user's cash
        rows = db.execute("SELECT * FROM users WHERE id = :user_id",
                          user_id=session["user_id"])
        session["cash"] = rows[0]["cash"]

        # Calculate and update users cash
        cash = session["cash"] + income

        db.execute("UPDATE users SET cash=? WHERE id=?", cash,
                   session["user_id"])

        print(rows)

        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
