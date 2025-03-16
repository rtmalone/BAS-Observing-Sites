from flask import Flask, render_template, request, redirect, url_for, flash, session
from decimal import Decimal
from dotenv import load_dotenv
import googlemaps
import os
import jwt
import secrets
from datetime import datetime, timedelta, UTC
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import mysql.connector
from mysql.connector import Error

# Load environment variables
load_dotenv()

# Verify required environment variables are set
if not os.getenv('SECRET_KEY'):
    raise ValueError("No SECRET_KEY set for Flask application")
if not os.getenv('MYSQL_DATABASE'):
    raise ValueError("No MYSQL_DATABASE set for Flask application")

# Initialize Google Maps client
if os.getenv('GOOGLE_MAPS_API_KEY') and os.getenv('GOOGLE_MAPS_API_KEY') != 'your_google_maps_api_key_here':
    gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))
else:
    print("Warning: No valid Google Maps API key provided. Map functionality will be disabled.")
    gmaps = None

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['DEBUG'] = False  # Enable debug mode

def get_db_connection():
    """Get a MySQL database connection"""
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST'),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE')
    )

def init_db():
    """Initialize the database tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(120) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create magic_tokens table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS magic_tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            token VARCHAR(255) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Create locations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(100) NOT NULL,
            email VARCHAR(120) NOT NULL,
            latitude FLOAT NOT NULL,
            longitude FLOAT NOT NULL,
            description TEXT NOT NULL,
            show_email BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # Add initial user if not exists
    cursor.execute('SELECT id FROM users WHERE email = %s', ('rtylermalone@gmail.com',))
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (name, email) VALUES (%s, %s)
        ''', ('Tyler Malone', 'rtylermalone@gmail.com'))
    
    conn.commit()
    cursor.close()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def send_magic_link(email: str, token: str):
    """Send magic link email to user"""
    msg = MIMEMultipart()
    msg['From'] = "your-email@example.com"  # Replace with your email
    msg['To'] = email
    msg['Subject'] = "Your Magic Link for BAS Observing Sites"
    
    magic_link = f"http://localhost:5000/verify/{token}"  # Updated port to 5001
    body = f"""
    Hello!
    
    Click the link below to sign in to BAS Observing Sites:
    
    {magic_link}
    
    This link will expire in 1 hour.
    
    If you didn't request this link, you can safely ignore this email.
    """
    
    msg.attach(MIMEText(body, 'plain'))
    
    # For development, just print the magic link
    print(f"Magic Link (Development Only): {magic_link}")
    
    # TODO: Configure email sending in production
    # with smtplib.SMTP('smtp.gmail.com', 587) as server:
    #     server.starttls()
    #     server.login("your-email@gmail.com", "your-password")
    #     server.send_message(msg)

def generate_magic_token(user_id: int) -> str:
    """Generate a new magic token for a user"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO magic_tokens (user_id, token, expires_at)
        VALUES (%s, %s, %s)
    ''', (user_id, token, expires_at))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return token

@app.route('/')
def login():
    if 'user_id' in session:
        return redirect(url_for('add_location'))
    return render_template('login.html')

@app.route('/request-magic-link', methods=['POST'])
def request_magic_link():
    email = request.form.get('email')
    if not email:
        flash('Please provide an email address.', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
    user = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not user:
        flash('No account found with this email address.', 'error')
        return redirect(url_for('login'))
    
    token = generate_magic_token(user['id'])
    send_magic_link(email, token)
    
    flash('Magic link has been sent to your email!', 'success')
    return redirect(url_for('login'))

@app.route('/verify/<token>')
def verify_magic_link(token):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT mt.user_id, mt.expires_at, mt.used, u.email, u.name
        FROM magic_tokens mt
        JOIN users u ON mt.user_id = u.id
        WHERE mt.token = %s AND mt.used = FALSE
    ''', (token,))
    magic_token = cursor.fetchone()
    
    if not magic_token:
        flash('Invalid or expired magic link.', 'error')
        return redirect(url_for('login'))
    
    # Convert MySQL TIMESTAMP to Python datetime with UTC timezone
    expires_at = magic_token['expires_at'].replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        flash('This magic link has expired.', 'error')
        return redirect(url_for('login'))
    
    # Mark token as used
    cursor.execute('UPDATE magic_tokens SET used = TRUE WHERE token = %s', (token,))
    conn.commit()
    
    # Set session
    session['user_id'] = magic_token['user_id']
    session['user_email'] = magic_token['email']
    session['user_name'] = magic_token['name']
    
    cursor.close()
    conn.close()
    
    return redirect(url_for('add_location'))

@app.route('/logout')
def logout():
    if 'user_id' in session:
        # Invalidate all unused magic tokens for this user
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE magic_tokens SET used = TRUE WHERE user_id = %s AND used = FALSE', 
                      (session['user_id'],))
        conn.commit()
        cursor.close()
        conn.close()
    
    session.clear()  # Clear all session data
    return redirect(url_for('login'))

@app.route('/add-location', methods=['GET', 'POST'])
@login_required
def add_location():
    if request.method == 'POST':
        title = request.form['title']
        email = request.form['email']
        lat = float(request.form['latitude'])
        lon = float(request.form['longitude'])
        description = request.form['description']
        show_email = 'show_email' in request.form
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check for duplicate location
        cursor.execute('''
            SELECT id FROM locations
            WHERE ABS(latitude - %s) < 0.001 AND ABS(longitude - %s) < 0.001
        ''', (lat, lon))
        
        if cursor.fetchone():
            flash('A location already exists at these coordinates!', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('add_location'))
        
        # Add new location
        cursor.execute('''
            INSERT INTO locations (title, email, latitude, longitude, description, show_email)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (title, email, lat, lon, description, show_email))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Location added successfully!', 'success')
        return redirect(url_for('add_location'))
    
    return render_template('form.html', google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

@app.route('/map')
@login_required
def view_map():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT * FROM locations')
    locations = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('map.html', 
                         locations=locations,
                         google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

@app.route('/api/map-data')
@login_required
def get_map_data():
    """Secure endpoint to get map data"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT * FROM locations')
    locations = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    def get_directions_url(lat: float, lng: float) -> str:
        """Generate Google Maps directions URL"""
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
    
    map_data = {
        'center': {'lat': 35.0456, 'lng': -85.3097},
        'zoom': 10,
        'markers': [
            {
                'position': {'lat': loc['latitude'], 'lng': loc['longitude']},
                'title': loc['title'],
                'info': {
                    'title': loc['title'],
                    'description': loc['description'],
                    'email': loc['email'] if loc.get('show_email', False) else None,
                    'directions_url': get_directions_url(loc['latitude'], loc['longitude'])
                }
            }
            for loc in locations
        ]
    }
    return map_data

if __name__ == '__main__':
    init_db()  # Initialize database tables
    app.run(debug=True) 