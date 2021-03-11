import os

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


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # sets variable for user id
    user_id = session["user_id"]

    # update prices, so you can see if you have made profit or loss
    alles = db.execute("SELECT * FROM stocks WHERE id = :user_id",
                       user_id=user_id)
    for row in alles:
        zoeken = lookup(row["symbol"])
        db.execute("UPDATE stocks SET total_price = :newprice WHERE symbol = :symbol",
                   newprice=int(zoeken["price"]) * row["nr_of_shares"], symbol=row["symbol"])

    # set price and total price in USD
    updated_alles = db.execute("SELECT * FROM stocks WHERE id = :user_id",
                               user_id=session["user_id"])
    for row in updated_alles:
        zoeken = lookup(row["symbol"])
        row["total_price"] = usd(row["total_price"])
        row["price"] = usd(int(zoeken["price"]))

    cash = db.execute("SELECT * FROM users WHERE id = :user_id",
                      user_id=user_id)
    doekoe = usd(int(cash[0]["cash"]))

    # do if user has no stocks
    if db.execute("SELECT SUM(total_price) FROM stocks WHERE id = :user_id",
                  user_id=user_id)[0]["SUM(total_price)"] == None:
        wallet = doekoe

    # do if user has stocks
    else:
        sum_stocks = db.execute("SELECT SUM(total_price) FROM stocks WHERE id = :user_id",
                                user_id=user_id)
        som_aandelen = sum_stocks[0]["SUM(total_price)"]
        wallet = usd(int(cash[0]["cash"]) + som_aandelen)

    return render_template("index.html", rows=updated_alles, amount=doekoe, som=wallet)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        user_id = session["user_id"]

        # searches for price and name of symbol
        zoeken = lookup(symbol)

        # check if symbol is empty or invalid
        if not symbol:
            return apology("Symbol can not be empty", 400)
        if zoeken == None:
            return apology("Symbol does not exist", 400)

        # checks if number of shares is empty
        if shares == None or not shares:
            return apology("YOU MUST SELECT A MINIMUM OF 1 SHARE", 400)

        # checks if number of shares is numeric
        if not shares.isdigit():
            return apology("YOU MUST SELECT A MINIMUM OF 1 SHARE", 400)

        # checks if number of shares isn't a fraction
        if float(shares) % 1 != 0:
            return apology("YOU MUST SELECT A MINIMUM OF 1 SHARE", 400)

        # checks if number of shares is > 0
        if int(shares) < 1:
            return apology("YOU MUST SELECT A MINIMUM OF 1 SHARE", 400)

        # sets variable for price
        price = zoeken["price"]

        # selects amount of cash of user
        cash = db.execute("SELECT * FROM users WHERE id = :user_id",
                          user_id=user_id)

        # checks if user has enough money
        if (int(zoeken["price"]) * int(shares)) > cash[0]["cash"]:
            return apology("You do not have enough cash to purchase!", 400)

        # puts users purchase in buy database
        db.execute("INSERT INTO buy (id, symbol, price, nr_of_shares, total_price) VALUES(:user_id, :symbol, :price, :nr_of_shares, :total_price)",
                   user_id=user_id, symbol=symbol, price=price, nr_of_shares=shares, total_price=int(price) * int(shares))

        # checks if user has not bought this share, puts new share in stocks database
        if not db.execute("SELECT * FROM stocks WHERE symbol = :symbol AND id = :user_id",
                          symbol=symbol, user_id=user_id):
            db.execute("INSERT INTO stocks (id, symbol, nr_of_shares, total_price) VALUES(:user_id, :symbol, :nr_of_shares, :total_price)",
                       user_id=user_id, symbol=symbol, nr_of_shares=shares, total_price=int(price) * int(shares))

        # if user already has this share, updates info in stocks
        else:
            nr_shares = db.execute("SELECT nr_of_shares FROM stocks WHERE symbol = :symbol AND id = :user_id",
                                   symbol=symbol, user_id=user_id)[0]["nr_of_shares"] + int(request.form.get("shares")[0])
            db.execute("UPDATE stocks SET nr_of_shares = :new_nr_shares, total_price = :new_total_price WHERE symbol = :symbol AND id = :user_id",
                       new_nr_shares=nr_shares, new_total_price=int(price) * nr_shares, symbol=symbol, user_id=user_id)

        # updates users current cash
        db.execute("UPDATE users SET cash = :updcash WHERE id = :user_id",
                   updcash=cash[0]["cash"] - (int(price) * int(shares)), user_id=user_id)

        return redirect("/")

    return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    # sets username
    username = request.args.get("username")

    # checks if username is not empty
    if not len(str(username)) > 0:
        return jsonify(False)

    # select all usernames
    gebruikte_un = db.execute("SELECT username FROM users")

    # checks if username is in username database
    for un in gebruikte_un:
        if un["username"] == username:
            return jsonify(False)

    return jsonify(True)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    user_id = session["user_id"]

    # get tables for all stocks bought and sold for user
    allesgekocht = db.execute("SELECT * FROM buy WHERE id = :user_id ORDER BY time ",
                              user_id=user_id)
    allesverkocht = db.execute("SELECT * FROM sell WHERE id = :user_id ORDER BY time ",
                               user_id=user_id)

    # change price to usd
    for row in allesgekocht:
        row["price"] = usd(row["price"])
    for row in allesverkocht:
        row["price"] = usd(row["price"])

    return render_template("history.html", buyrows=allesgekocht, sellrows=allesverkocht)


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":

        user_id = session["user_id"]

        deposit = request.form.get("deposit")

        # checks if deposit is empty
        if deposit == None or not deposit:
            return apology("YOU MUST SELECT A MINIMUM OF 1 DOLLAR", 400)

        # checks if number of deposit is numeric
        if not deposit.isdigit():
            return apology("YOU MUST SELECT A MINIMUM OF 1 DOLLAR", 400)

        # checks if number of deposit isn't a fraction
        if float(deposit) % 1 != 0:
            return apology("YOU MUST SELECT A WHOLE AMOUNT OF MONEY", 400)

        # checks if number of deposit is > 0
        if int(deposit) < 1:
            return apology("YOU MUST SELECT A MINIMUM OF 1 DOLLAR", 400)

        #
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=user_id)
        new_cash = int(cash[0]["cash"]) + int(deposit)

        db.execute("UPDATE users SET cash = :new_cash WHERE id = :user_id",
                   new_cash=new_cash, user_id=user_id)

        return redirect("/")

    return render_template("deposit.html")


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
    if request.method == "POST":

        symbol = request.form.get("symbol")

        # searches for price and name of symbol
        zoeken = lookup(symbol)

        # check if symbol is empty or invalid
        if not symbol:
            return apology("Symbol can not be empty", 400)
        if zoeken == None:
            return apology("Symbol does not exist", 400)

        return render_template("quoted.html", name=zoeken["name"], price=usd(zoeken["price"]), symbol=symbol)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # checks if username is not empty
        if not request.form.get("username"):
            return apology("Username can not be empty", 400)

        # checks if username is available
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        if len(rows) >= 1:
            return apology("Username already exists", 400)

        # checks if password and confirmation are not empty
        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("Password can not be empty", 400)

        # checks if password and confirmation match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Your password doesn't match", 400)

        # inserts data into database, and hashes password
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :password)",
                   username=request.form.get("username"), password=generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8))

        # return to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        # set user given variables
        shares = request.form.get("shares")
        symbol = request.form.get("symbol")
        user_id = session["user_id"]

        # checks if number of shares is empty
        if shares == None or not shares:
            return apology("YOU MUST SELECT A MINIMUM OF 1 SHARE", 400)

        # checks if number of shares is numeric
        if not shares.isdigit():
            return apology("YOU MUST SELECT A MINIMUM OF 1 SHARE", 400)

        # checks if number of shares isn't a fraction
        if float(shares) % 1 != 0:
            return apology("YOU MUST SELECT A MINIMUM OF 1 SHARE", 400)

        # checks if number of shares is > 0
        if int(shares) < 1:
            return apology("YOU MUST SELECT A MINIMUM OF 1 SHARE", 400)

        stock = db.execute("SELECT * FROM stocks WHERE id= :user_id AND symbol = :symbol",
                           user_id=user_id, symbol=symbol)

        nr_shares = stock[0]["nr_of_shares"]

        # checks if user has the shares he wants to sell
        if int(shares) > nr_shares:
            return apology("YOU HAVE SELECTED TOO MANY SHARES", 400)

        new_nr = nr_shares - int(shares)

        # lookup stats about the symbol
        zoeken = lookup(symbol)

        # selects amount of cash of user
        cash = db.execute("SELECT * FROM users WHERE id = :user_id",
                          user_id=user_id)
        # delete stock from database stocks if user sells all stocks
        if new_nr == 0:
            db.execute("DELETE FROM stocks WHERE symbol = :symbol AND id = :user_id",
                       user_id=user_id, symbol=symbol)
        else:
            db.execute("UPDATE stocks SET nr_of_shares = :new_nr WHERE id = :user_id AND symbol = :symbol",
                       new_nr=new_nr, user_id=user_id, symbol=symbol)

        # updates users current cash
        db.execute("UPDATE users SET cash = :updcash WHERE id = :user_id",
                   updcash=cash[0]["cash"] + (int(zoeken["price"]) * int(shares)), user_id=user_id)

        # add sell into database
        db.execute("INSERT INTO sell (id, symbol, price, nr_of_shares, total_price) VALUES(:user_id, :symbol, :price, :nr_of_shares, :total_price)",
                   user_id=user_id, symbol=symbol, price=zoeken["price"], nr_of_shares=shares, total_price=int(zoeken["price"]) * int(shares))

        return redirect("/")

    all_stocks = db.execute("SELECT * FROM stocks WHERE id = :user_id",
                            user_id=session["user_id"])

    return render_template("sell.html", rows=all_stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)