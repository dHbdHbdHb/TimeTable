from flask import Flask,render_template, send_from_directory
import time
import datetime
import os, glob

app=Flask(__name__,
          static_url_path='')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
image_folder = os.path.join('static', 'images')

def get_latest_image():
    images = os.listdir(image_folder)
    images.sort(key=lambda x: os.path.getmtime(os.path.join(image_folder, x)))
    latest_image = images[-1]
    return latest_image

@app.route('/')
def index():
    latest_image = get_latest_image()
    return render_template('index.html', image_name=latest_image)

@app.route('/images/<path:path>')
def serve_image(path):
    return send_from_directory(image_folder, path)

if __name__== '__main__':
    app.run(host='0.0.0.0',debug=True)

while True:
    time.sleep(150)