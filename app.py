from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from decimal import Decimal
from dotenv import load_dotenv
import googlemaps
import os

# Load environment variables
load_dotenv()

# Verify required environment variables are set
if not os.getenv('SECRET_KEY'):
    raise ValueError("No SECRET_KEY set for Flask application")

# Initialize Google Maps client
gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///locations.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # Required for flash messages
db = SQLAlchemy(app)

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

@app.route('/', methods=['GET', 'POST'])
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