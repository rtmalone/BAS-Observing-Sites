from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from decimal import Decimal
from dotenv import load_dotenv
import googlemaps
import os
from functools import wraps
import requests
from datetime import timedelta

# Load environment variables
load_dotenv()

# Verify required environment variables are set
if not os.getenv('SECRET_KEY'):
    raise ValueError("No SECRET_KEY set for Flask application")
if not os.getenv('MYSQL_DATABASE'):
    raise ValueError("No MYSQL_DATABASE set for Flask application")
if not os.getenv('JOINIT_CLIENT_ID'):
    raise ValueError("No JOINIT_CLIENT_ID set for Flask application")
if not os.getenv('JOINIT_CLIENT_SECRET'):
    raise ValueError("No JOINIT_CLIENT_SECRET set for Flask application")

# Initialize Google Maps client
gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))

app = Flask(__name__)

# Session configuration
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)  # Sessions last 24 hours
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}@"
    f"{os.getenv('MYSQL_HOST')}/{os.getenv('MYSQL_DATABASE')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # Required for flash messages
db = SQLAlchemy(app)

JOINIT_AUTH_URL = "https://app.joinit.com/oauth2/authorize"
JOINIT_TOKEN_URL = "https://app.joinitapi.com/oauth2/token"

# Development mock settings
DEV_MODE = True  # Set to False in production
MOCK_USER = {
    'username': 'test_user',
    'email': 'test@barnardastro.org',
    'member_id': '12345'
}
app.config['DEV_MODE'] = DEV_MODE

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f'<Location {self.title}>'

def is_duplicate_location(lat: float, lon: float) -> bool:
    """Check if location exists within 0.001 degrees of lat/lon"""
    locations = Location.query.all()
    for loc in locations:
        if (abs(Decimal(str(loc.latitude)) - Decimal(str(lat))).quantize(Decimal('0.001')) == 0 and 
            abs(Decimal(str(loc.longitude)) - Decimal(str(lon))).quantize(Decimal('0.001')) == 0):
            return True
    return False

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session:
            flash('Please log in first', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    if 'authenticated' in session:
        return redirect(url_for('add_location'))
    return render_template('auth.html', google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

@app.route('/authenticate', methods=['POST'])
def authenticate():
    if DEV_MODE:
        # Mock successful authentication
        session.permanent = True  # Make session permanent
        session['authenticated'] = True
        session['username'] = MOCK_USER['username']
        session['email'] = MOCK_USER['email']
        session['member_id'] = MOCK_USER['member_id']
        flash('Development mode: Successfully authenticated', 'success')
        return redirect(url_for('add_location'))
    
    auth_params = {
        'response_type': 'code',
        'client_id': os.getenv('JOINIT_CLIENT_ID'),
        'redirect_uri': os.getenv('JOINIT_REDIRECT_URI'),
        'state': os.urandom(16).hex()  # Generate random state
    }
    
    # Store state in session to verify later
    session['oauth_state'] = auth_params['state']
    
    # Redirect to JoinIt's authorization URL
    auth_url = f"{JOINIT_AUTH_URL}?{'&'.join(f'{k}={v}' for k, v in auth_params.items())}"
    return redirect(auth_url)

@app.route('/callback')
def oauth_callback():
    if DEV_MODE:
        return redirect(url_for('add_location'))
    
    # Verify state to prevent CSRF
    if request.args.get('state') != session.get('oauth_state'):
        flash('Invalid state parameter', 'error')
        return redirect(url_for('home'))
    
    # Exchange code for token
    code = request.args.get('code')
    if not code:
        flash('Authorization failed', 'error')
        return redirect(url_for('home'))
    
    token_data = {
        'client_id': os.getenv('JOINIT_CLIENT_ID'),
        'client_secret': os.getenv('JOINIT_CLIENT_SECRET'),
        'code': code
    }
    
    try:
        response = requests.post(JOINIT_TOKEN_URL, data=token_data)
        response.raise_for_status()
        token_info = response.json()
        
        # Store the access token and mark as authenticated
        session['access_token'] = token_info['access_token']
        session['authenticated'] = True
        
        flash('Successfully authenticated', 'success')
        return redirect(url_for('add_location'))
        
    except requests.exceptions.RequestException as e:
        flash('Authentication failed', 'error')
        return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('home'))

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_location():
    if request.method == 'POST':
        title = request.form['title']
        email = request.form['email']
        lat = float(request.form['latitude'])
        lon = float(request.form['longitude'])
        description = request.form['description']

        if is_duplicate_location(lat, lon):
            flash('A location already exists at these coordinates!', 'error')
            return redirect('/')

        new_location = Location(
            title=title,
            email=email,
            latitude=lat,
            longitude=lon,
            description=description
        )
        db.session.add(new_location)
        db.session.commit()
        flash('Location added successfully!', 'success')
        return redirect('/')

    return render_template('form.html', google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

@app.route('/map')
def view_map():
    locations = Location.query.all()
    location_data = [
        {
            'title': loc.title,
            'email': loc.email,
            'latitude': loc.latitude,
            'longitude': loc.longitude,
            'description': loc.description
        }
        for loc in locations
    ]
    return render_template('map.html', 
                         locations=location_data,
                         google_maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY'))

@app.route('/api/map-data')
def get_map_data():
    """Secure endpoint to get map data"""
    locations = Location.query.all()
    
    def get_directions_url(lat: float, lng: float) -> str:
        """Generate Google Maps directions URL"""
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"

    map_data = {
        'center': {'lat': 35.0456, 'lng': -85.3097},
        'zoom': 10,
        'markers': [
            {
                'position': {'lat': loc.latitude, 'lng': loc.longitude},
                'title': loc.title,
                'info': {
                    'title': loc.title,
                    'description': loc.description,
                    'email': loc.email,
                    'directions_url': get_directions_url(loc.latitude, loc.longitude)
                }
            }
            for loc in locations
        ]
    }
    return map_data

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 