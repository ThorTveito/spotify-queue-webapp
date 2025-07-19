from flask import Flask, redirect, request, session, jsonify, render_template
import requests
import time
import os
import base64
from urllib.parse import urlencode
from dotenv import load_dotenv
import urllib.parse


app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.urandom(24)

load_dotenv()  # load values from .env into environment variables

from typing import Literal
ENV_NAME = os.getenv('ENV_NAME', 'DEV')
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')
access_token = os.getenv('SPOTIFY_ACCESS_TOKEN')
refresh_token = os.getenv('SPOTIFY_REFRESH_TOKEN')
token_expires_at = 0  # timestamp when token expires, init 0

# Spotify URLs
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
SEARCH_URL = 'https://api.spotify.com/v1/search'

# Scope needed for queueing
SCOPE = 'user-modify-playback-state'


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    error = request.args.get('error')
    if error:
        return f"Error during authorization: {error}", 400
    if not code:
        return "No code provided", 400

    # Exchange code for tokens
    token_url = 'https://accounts.spotify.com/api/token'
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }

    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return f"Failed to get tokens: {response.text}", 400

    tokens = response.json()
    access_token = tokens.get('access_token')
    refresh_token = tokens.get('refresh_token')

    print(f"ACCESS TOKEN:\n{access_token}\n")
    print(f"REFRESH TOKEN:\n{refresh_token}\n")

    # Optional: Save tokens to a local file (be sure to keep this secure)
    with open('spotify_tokens.txt', 'w') as f:
        f.write(f"ACCESS_TOKEN={access_token}\n")
        f.write(f"REFRESH_TOKEN={refresh_token}\n")

    return '''
        <h1>Authorization Complete</h1>
        <p>Tokens received and saved to <code>spotify_tokens.txt</code>.</p>
        <p>Check your console output too.</p>
        <p>You can now close this window and update your .env file with these tokens.</p>
    '''

@app.route('/login')
def login():
    scope = 'user-read-playback-state user-modify-playback-state'
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': scope,
        'show_dialog': 'true'
    }
    url = 'https://accounts.spotify.com/authorize?' + urllib.parse.urlencode(params)
    return redirect(url)

def refresh_access_token():
    global access_token, refresh_token, token_expires_at

    resp = requests.post('https://accounts.spotify.com/api/token', data={
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    })
    resp.raise_for_status()
    tokens = resp.json()
    access_token = tokens['access_token']
    # Spotify refresh token usually does not change, but update if present
    if 'refresh_token' in tokens:
        refresh_token = tokens['refresh_token']

    # Set token expiry time 1 hour from now minus a few seconds buffer
    token_expires_at = time.time() + tokens.get('expires_in', 3600) - 60


def get_access_token():
    global token_expires_at
    if time.time() > token_expires_at:
        refresh_access_token()
    return access_token



@app.route('/search')
def search():
    q = request.args.get('q')
    if not q:
        return jsonify({"error": "Missing search query parameter 'q'"}), 400

    token = get_access_token()
    headers = {'Authorization': f'Bearer {token}'}
    params = {'q': q, 'type': 'track', 'limit': 5}
    r = requests.get('https://api.spotify.com/v1/search', headers=headers, params=params)
    r.raise_for_status()
    return jsonify(r.json())


@app.route('/queue', methods=['POST'])
def queue_track():
    data = request.get_json()
    track_uri = data.get('uri')
    if not track_uri:
        return jsonify({'error': 'Missing track URI'}), 400

    token = get_access_token()
    headers = {'Authorization': f'Bearer {token}'}
    params = {'uri': track_uri}
    r = requests.post('https://api.spotify.com/v1/me/player/queue', headers=headers, params=params)

    if r.status_code == 204:
        return jsonify({'status': 'queued'})
    else:
        try:
            error_data = r.json()
        except ValueError:
            error_data = r.text
        return jsonify({'error': error_data, 'status_code': r.status_code}), r.status_code


@app.route('/current-track')
def current_track():
    token = get_access_token()
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers=headers)
    
    if r.status_code == 200:
        data = r.json()
        # Add calculated progress percentage
        if data and 'progress_ms' in data and 'item' in data and data['item']:
            progress_ms = data['progress_ms']
            duration_ms = data['item']['duration_ms']
            progress_percentage = (progress_ms / duration_ms * 100) if duration_ms > 0 else 0
            
            # Add formatted time strings
            def format_time(ms):
                seconds = ms // 1000
                minutes = seconds // 60
                seconds = seconds % 60
                return f"{minutes}:{seconds:02d}"
            
            data['progress_formatted'] = format_time(progress_ms)
            data['duration_formatted'] = format_time(duration_ms)
            data['progress_percentage'] = progress_percentage
            
        return jsonify(data)
    elif r.status_code == 204:
        return jsonify({'error': 'No track currently playing'}), 204
    else:
        try:
            error_data = r.json()
        except ValueError:
            error_data = r.text
        return jsonify({'error': error_data, 'status_code': r.status_code}), r.status_code


@app.route('/get-queue')
def get_queue():
    token = get_access_token()
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get('https://api.spotify.com/v1/me/player/queue', headers=headers)
    
    if r.status_code == 200:
        return jsonify(r.json())
    else:
        try:
            error_data = r.json()
        except ValueError:
            error_data = r.text
        return jsonify({'error': error_data, 'status_code': r.status_code}), r.status_code

@app.route('/health')
def health():
    return "", 200


if __name__ == '__main__':
    print(f"Starting server as {ENV_NAME}")
    if (ENV_NAME == 'PROD'):
        from waitress import serve
        serve(app, host='0.0.0.0', port=8080)
    elif (ENV_NAME == 'DEV'):
        app.run(debug=True)
    else:
        print(f"Unknown ENV_NAME {ENV_NAME}")
