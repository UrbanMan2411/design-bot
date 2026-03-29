#!/usr/bin/env python3
"""
Simple proxy server for LandingAI web interface.
Hides API keys from client-side code.
"""

from flask import Flask, request, jsonify, send_from_directory
import requests
import os

app = Flask(__name__, static_folder='web')

OPENROUTER_URL = os.getenv('OPENROUTER_URL', 'http://82.24.110.51:20128/v1/chat/completions')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'UrbanMan2411/design-pages')


@app.route('/')
def index():
    return send_from_directory('web', 'index.html')


@app.route('/api/generate', methods=['POST'])
def generate():
    """Proxy to AI API."""
    data = request.json
    resp = requests.post(OPENROUTER_URL, json=data, timeout=120)
    return jsonify(resp.json()), resp.status_code


@app.route('/api/publish', methods=['POST'])
def publish():
    """Publish HTML to GitHub Pages."""
    data = request.json
    filename = data.get('filename')
    html = data.get('html')
    
    import base64
    content = base64.b64encode(html.encode()).decode()
    path = f"designs/{filename}.html"
    
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github+json',
    }
    
    # Check if exists
    check = requests.get(
        f'https://api.github.com/repos/{GITHUB_REPO}/contents/{path}',
        headers=headers
    )
    
    body = {
        'message': f'Add design: {filename}',
        'content': content,
        'branch': 'main',
    }
    if check.status_code == 200:
        body['sha'] = check.json()['sha']
    
    resp = requests.put(
        f'https://api.github.com/repos/{GITHUB_REPO}/contents/{path}',
        headers=headers,
        json=body,
    )
    
    return jsonify({'status': 'ok', 'url': f'https://urbanman2411.github.io/design-pages/designs/{filename}.html'}), resp.status_code


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
