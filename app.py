from flask import Flask,render_template,Response, send_from_directory
import time
import os

app=Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
image_folder = os.path.join('static', 'images')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/images/<path:path>')
def serve_image(path):
    return send_from_directory(image_folder, 'display_table.png')

# No caching at all for API endpoints.
@app.after_request
def add_header(response):
    # response.cache_control.no_store = True
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-store'
    return response

if __name__== '__main__':
    app.run(host='0.0.0.0',debug=True)

while True:
    time.sleep(150)