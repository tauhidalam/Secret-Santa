from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import random
import string
import os
from waitress import serve

app = Flask(__name__)

# Set SECRET_KEY from environment variable, or use a fallback key for local development
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-very-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///fallback.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    unique_code = db.Column(db.String(6), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wishlist_name = db.Column(db.String(100), nullable=False)
    product_url = db.Column(db.String(200), nullable=True)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    giver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Function to generate a 6-digit unique code
def generate_unique_code(name):
    initials = ''.join([part[0].upper() for part in name.split()][:2])  # Take first two initials
    random_digits = ''.join(random.choices(string.digits, k=4))  # Generate 4 random digits
    return f"{initials}{random_digits}"

# Routes
@app.route('/')
def home():
    return render_template('login.html')  # This will prompt the user to enter their code

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user.is_admin:
        return redirect(url_for('wishlist'))  # Non-admin users are redirected to wishlist page
    
    if request.method == 'POST':
        name = request.form.get('name')
        unique_code = generate_unique_code(name)
        new_user = User(name=name, unique_code=unique_code)
        db.session.add(new_user)
        db.session.commit()
        flash(f'User {name} added with code: {unique_code}')
        return redirect(url_for('admin'))  # Stay on the admin page after registration
    
    # Fetch all users (including admin)
    users = User.query.all()

    # Fetch all matches and join the Match model with User to get giver and receiver
    # Exclude admin from matches
    matched_users = db.session.query(Match, User).join(User, Match.giver_id == User.id).filter(User.is_admin == False).all()

    # Prepare the data for matched users, adding the receiver information
    matched_users_info = []
    for match, giver in matched_users:
        receiver = User.query.get(match.receiver_id)  # Get receiver based on receiver_id
        matched_users_info.append((giver.name, receiver.name))

    return render_template('admin.html', users=users, matched_users_info=matched_users_info)


@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user.is_admin:
        return redirect(url_for('wishlist'))  # Non-admin users are redirected to wishlist page

    user_to_delete = User.query.get_or_404(user_id)
    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f'User {user_to_delete.name} has been deleted.')
    return redirect(url_for('admin'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        unique_code = request.form.get('unique_code')
        user = User.query.filter_by(unique_code=unique_code).first()
        if user:
            session['user_id'] = user.id
            if user.is_admin:
                return redirect(url_for('admin'))  # Redirect to admin page if user is admin
            else:
                return redirect(url_for('wishlist'))  # Redirect to wishlist page if user is not admin
        flash('Invalid code, please try again.')
    return render_template('login.html')  # Render the login page to enter the 6-digit code

@app.route('/wishlist', methods=['GET', 'POST'])
def wishlist():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    user = User.query.get(user_id)  # Load user from the database

    # Check if the user is matched
    match = Match.query.filter_by(giver_id=user_id).first()
    if not match:
        match = Match.query.filter_by(receiver_id=user_id).first()

    if match:
        # User has been matched, show the matched user's wishlist
        matched_user_id = match.receiver_id if match.giver_id == user_id else match.giver_id
        matched_user = User.query.get(matched_user_id)
        user_wishlist = Wishlist.query.filter_by(user_id=matched_user_id).all()
        return render_template('wishlist.html', user=user, wishlist=user_wishlist, matched_user=matched_user)

    # If not matched, allow the user to modify their wishlist
    if request.method == 'POST':
        wishlist_name = request.form.get('wishlist_name')
        product_url = request.form.get('product_url')
        wishlist_count = Wishlist.query.filter_by(user_id=user_id).count()
        if wishlist_count < 3:
            new_wish = Wishlist(user_id=user_id, wishlist_name=wishlist_name, product_url=product_url)
            db.session.add(new_wish)
            db.session.commit()
            flash('Wishlist item added!')
        else:
            flash('Maximum of 3 items allowed.')

    user_wishlist = Wishlist.query.filter_by(user_id=user_id).all()
    return render_template('wishlist.html', user=user, wishlist=user_wishlist)


# Route to delete wishlist item
@app.route('/delete_wishlist_item/<int:item_id>', methods=['POST'])
def delete_wishlist_item(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    wishlist_item = Wishlist.query.get_or_404(item_id)
    
    if wishlist_item.user_id == session['user_id']:
        db.session.delete(wishlist_item)
        db.session.commit()
        flash('Wishlist item deleted!')
    else:
        flash('You can only delete your own wishlist items.')
    
    return redirect(url_for('wishlist'))  # Redirect back to wishlist page


def match_users():
    # Get all non-admin users
    users = User.query.filter_by(is_admin=False).all()
    user_ids = [user.id for user in users]

    # Shuffle the user list to randomize the matching process
    random.shuffle(user_ids)

    # Create the matches by pairing users
    matches = []
    for i in range(len(user_ids)):
        giver_id = user_ids[i]
        receiver_id = user_ids[(i + 1) % len(user_ids)]  # The next user in the list, last user is matched with the first
        matches.append((giver_id, receiver_id))

    # Store the matches in the database
    for giver_id, receiver_id in matches:
        new_match = Match(giver_id=giver_id, receiver_id=receiver_id)
        db.session.add(new_match)
    db.session.commit()

    return matches

@app.route('/admin/match', methods=['POST'])
def match():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user.is_admin:
        return redirect(url_for('wishlist'))  # Non-admin users are redirected to wishlist page

    # Call the match function
    matches = match_users()

    flash('Users have been successfully matched!')

    return redirect(url_for('admin'))

@app.route('/reset_matching', methods=['POST'])
def reset_matching():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user.is_admin:
        return redirect(url_for('wishlist'))  # Non-admin users are redirected to wishlist page

    print("Reset Matching initiated.")  # Debugging log to check if the function is triggered.

    # Step 1: Delete all matches
    Match.query.delete()
    db.session.commit()
    print("Matches deleted.")  # Debugging log for match deletion.

    # Step 2: Reset the matched status for all users
    users = User.query.all()
    for u in users:
        u.is_matched = False  # Assuming `is_matched` exists to prevent edits
    db.session.commit()
    print("User matched status reset.")  # Debugging log for resetting matched status.

    flash('Matches have been reset! Users can now edit their wishlists.')

    return redirect(url_for('admin'))  # Redirect back to the admin page



if __name__ == "__main__":
    serve(app, host='0.0.0.0', port=5000)
