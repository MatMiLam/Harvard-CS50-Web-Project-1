import os

from flask import Flask, session, render_template, request, redirect, jsonify, abort
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import error, login_required, lookup_goodreads

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# Register for a new account
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "GET":
        return render_template("register.html")

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        requiredFieldnames = ["username", "password", "confirmation"]

        # Ensure a username and a password was submitted
        for entry in requiredFieldnames:
            if not request.form.get(entry):                
                return  error("You must fill out all fields")     

        # Ensure password and confirmation password match
        if request.form.get("password") != request.form.get("confirmation"):            
            return  error("Passwords must match")    

        # Ensure user not alrady registered
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          {"username" : request.form.get("username")}).fetchone()
                          
        if rows:
            return render_template ("error.html", error_message="Username already exists")

        # Add new user to the database
        hash = generate_password_hash(request.form.get("password"))        

        new_id = db.execute(
            "INSERT INTO users(username, hash) VALUES(:username, :hash)",
            {"username": request.form.get("username"),            
            "hash": hash})
        db.commit()

        session["user_id"] = db.execute(
            "SELECT id FROM users WHERE username = :username", 
            {"username": username}).fetchone()[0]        

        return redirect("/")       


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Ensure username was submitted
        if not username:            
            return  error("You must provide username")    

        # Ensure password was submitted
        elif not password:            
            return  error("You must provide password")    

        # Query database for username
        row = db.execute("SELECT * FROM users WHERE username = :username",
                          {"username" : username}).fetchone()
       
        # Ensure username exists and password is correct
        if row == None or not check_password_hash(row.hash, password):            
            return  error("Invalid username and/or password")    

        # Remember which user has logged in
        session["user_id"] = row.id

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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():    

    if request.method == "POST":
        search = request.form.get("search")

        search_results = db.execute("SELECT * FROM books WHERE isbn LIKE :search OR lower(title) LIKE :search OR lower(author) LIKE :search",
                    {"search" : f"%{search.lower()}%"}).fetchall()        

    return render_template("search_results.html", search_results=search_results)
    
    
@app.route("/books/<int:book_id>")
@login_required
def book(book_id):
    """Lists details about a single book."""

    # Check book info
    book = db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).fetchone()
    print()
    print(book)
    if book is None:        
        return  error("No such book")    
        
    else:
        goodreads_data = lookup_goodreads(book.isbn)

    user_reviews = db.execute("SELECT * FROM reviews WHERE book_id = :book_id", {"book_id": book_id}).fetchall()

    # Check if user has already reviewed 
    reviewed = False
    for review in user_reviews:
        if review.user_id == session["user_id"]:
            reviewed = True    

    ratings = goodreads_data["books"][0]["work_ratings_count"]
    rating = goodreads_data["books"][0]["average_rating"]             

    return render_template("book.html", book=book, ratings=ratings, rating=rating, user_reviews=user_reviews, reviewed=reviewed)


@app.route("/review", methods=["POST"])
@login_required
def review():
    
    if request.method == "POST":
        user_rating = request.form.get("rating")
        user_review = request.form.get("review")
        book_id = request.form.get("book_id")               

        # Verify valid user review input
        if not user_rating or not user_review:
                return  error("You must submit a rating and a review")

        review_check = db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id", {"user_id": session["user_id"], "book_id": book_id}).fetchone()

        # Enter review into database 
        if not review_check:
            new_review = db.execute(
            "INSERT INTO reviews(user_id, book_id, rating, review) VALUES(:user_id, :book_id, :rating, :review)", {"user_id": session["user_id"], "book_id": book_id, "rating": user_rating, "review": user_review})
            db.commit()
        else:
                return  error("You have already reviewed this book")        

    return redirect(f"/books/{book_id}")


@app.route("/api/<string:isbn>", methods=["GET"])
def api(isbn):

    isbn_check = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()    

    # Valid ISBN check 
    if not isbn_check:
        print("Returning 404")
        return abort(404)   
   
    api_data = lookup_goodreads(isbn)
    ratings = api_data["books"][0]["work_ratings_count"]
    rating = api_data["books"][0]["average_rating"]       

    # Build API dict  
    api_return = {
        "title": isbn_check.title,
        "author": isbn_check.author,
        "year": isbn_check.year,
        "isbn": isbn,
        "review_count": ratings,
        "average_score": rating,
    }

    return jsonify(api_return)