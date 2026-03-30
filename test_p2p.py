import requests
import json
from datetime import datetime
from PIL import Image
import piexif
import io
import time
import os

BASE_URL = "http://127.0.0.1:5000"

def create_dummy_image():
    # Create an image with some variance so it passes heuristic
    img = Image.new('RGB', (100, 100), color = 'red')
    pixels = img.load()
    for i in range(50):
        for j in range(50):
            pixels[i, j] = (0, 0, 255) # blue square to add variance

    # Add EXIF data with current time
    exif_dict = {"0th": {}, "Exif": {}, "1st": {}, "thumbnail": None, "GPS": {}}
    now_str = datetime.now().strftime('%Y:%m:%d %H:%M:%S')
    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = now_str.encode('utf-8')
    exif_bytes = piexif.dump(exif_dict)
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG', exif=exif_bytes)
    return img_byte_arr.getvalue()

def run_tests():
    print("Wait for server to start...")
    time.sleep(3)
    city = "London"
    
    # 1. Submit Report
    print(f"Submitting P2P report for {city}...")
    img_bytes = create_dummy_image()
    files = {'photo': ('test.jpg', img_bytes, 'image/jpeg')}
    data = {'city': city, 'choice': 'Rain'}
    
    res = requests.post(f"{BASE_URL}/report", files=files, data=data)
    print("Report Response:", res.json())
    
    # 2. Check Pending Report
    print("Checking pending report...")
    res = requests.get(f"{BASE_URL}/pending_report/{city}")
    pending_data = res.json()
    print("Pending Report Response:", pending_data)
    
    if not pending_data.get('exists'):
        print("FAILED: Report is not pending.")
        return
        
    report_id = pending_data['id']
    
    # 3. Submit 5 'yes' votes
    print(f"Submitting 5 'yes' votes for report {report_id}...")
    for i in range(5):
        res = requests.post(f"{BASE_URL}/vote/{report_id}", json={"vote": "yes"})
        print(f" Vote {i+1} Response:", res.json())
        
    # 4. Check main screen (via index route) for override message
    print(f"Checking index route for override message in {city}...")
    res = requests.post(f"{BASE_URL}/", data={"city": city})
    if "Verified Rain (Peer Consensus)" in res.text:
        print("SUCCESS! UI correctly overrode weather strictly based off 5 Local Rain Consensus Votes!")
    else:
        print("FAILED: UI did not show verified message.")

if __name__ == "__main__":
    os.system("pip install piexif -q")
    run_tests()

