from flask import Flask, redirect, request, session, jsonify
import requests
import os
import base64
from urllib.parse import urlencode
from dotenv import load_dotenv


app = Flask(__name__)
app.secret_key = os.urandom(24)

load_dotenv()  # load values from .env into environment variables

CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')

# Spotify URLs
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
SEARCH_URL = 'https://api.spotify.com/v1/search'

# Scope needed for queueing
SCOPE = 'user-modify-playback-state'


@app.route('/')
def index():
    return '<a href="/login">Login with Spotify</a>'


@app.route('/login')
def login():
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE
    }
    return redirect(f"{AUTH_URL}?{urlencode(params)}")


@app.route('/callback')
def callback():
    code = request.args.get('code')
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

    headers = {'Authorization': f'Basic {auth_header}'}
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }

    response = requests.post(TOKEN_URL, data=data, headers=headers)
    response_data = response.json()

    # Save access and refresh token in session (for testing only)
    session['access_token'] = response_data['access_token']
    session['refresh_token'] = response_data['refresh_token']

    return redirect('/search-ui')


@app.route('/search-ui')
def search_ui():
    return '''
        <form action="/search" method="get">
            <input type="text" name="q" placeholder="Search for a track" />
            <button type="submit">Search</button>
        </form>
    '''


@app.route('/search')
def search():
    query = request.args.get('q')
    access_token = session.get('access_token')

    if not access_token:
        return redirect('/login')

    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'q': query, 'type': 'track', 'limit': 5}

    r = requests.get(SEARCH_URL, headers=headers, params=params)
    if r.status_code != 200:
        return f"Spotify API error: {r.status_code} – {r.text}"

    return jsonify(r.json())


if __name__ == '__main__':
    app.run(debug=True)
