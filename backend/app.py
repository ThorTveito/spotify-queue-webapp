from flask import Flask, redirect, request, session, jsonify
import requests
import time
import os
import base64
from urllib.parse import urlencode
from dotenv import load_dotenv
import urllib.parse


app = Flask(__name__)
app.secret_key = os.urandom(24)

load_dotenv()  # load values from .env into environment variables

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


@app.route('/search-ui')
def search_ui():
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <title>Spotify Queue</title>
    </head>
    <body>
      <h1>Search Spotify and Queue a Track</h1>
      <input type="text" id="searchInput" placeholder="Search for a track" />
      <button onclick="search()">Search</button>
      <div id="results"></div>

      <script>
      async function search() {
        const query = document.getElementById('searchInput').value;
        const res = await fetch('/search?q=' + encodeURIComponent(query));
        if (!res.ok) {
          alert('Search failed: ' + res.status);
          return;
        }
        const data = await res.json();
        const tracks = data.tracks.items;
        const resultsDiv = document.getElementById('results');
        resultsDiv.innerHTML = '';

        tracks.forEach(track => {
          const div = document.createElement('div');
          div.innerHTML = `
            <strong>${track.name}</strong> by ${track.artists.map(a => a.name).join(', ')}
            <button onclick="queueTrack('${track.uri}')">Queue</button>
          `;
          resultsDiv.appendChild(div);
        });
      }

      async function queueTrack(uri) {
        const res = await fetch('/queue', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({uri})
        });
        if (res.ok) {
          alert('Track queued!');
        } else {
          const error = await res.json();
          alert('Error: ' + JSON.stringify(error));
        }
      }
      </script>
    </body>
    </html>
    '''


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


if __name__ == '__main__':
    app.run(debug=True)

