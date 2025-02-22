# BAS Observing Sites

A web application for the Barnard Astronomical Society to crowdsource and share information about public observation sites in the Chattanooga area.

## Overview

This application allows members to:
- Add new observation sites with detailed location information
- View all sites on an interactive map
- Get directions to observation sites

## Features

- **Interactive Map**: Shows all observation sites with detailed information
- **Location Search**: Search by address or input coordinates directly
- **Site Details**: Each location includes:
  - Title
  - Description
  - Contact email
  - Precise coordinates
  - Directions link

## Technical Stack

- **Backend**: Python/Flask
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: HTML/CSS with Google Maps JavaScript API
- **APIs**: Google Maps (Places, Directions)

## Setup

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file with:

```
GOOGLE_MAPS_API_KEY=your_api_key
SECRET_KEY=your_secret_key
```

4. Run the application:

```bash
python app.py
```

## Environment Variables

- `GOOGLE_MAPS_API_KEY`: Required for maps, geocoding, and places functionality
- `SECRET_KEY`: Required for Flask session management and security

## Contributing

This is an internal tool for the Barnard Astronomical Society. Please contact the society for contribution guidelines.

## License

This project is proprietary and for use by the Barnard Astronomical Society only.

