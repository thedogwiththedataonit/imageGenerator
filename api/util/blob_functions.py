import os
from concurrent.futures import ThreadPoolExecutor
import hashlib
import vercel_blob
from dotenv import load_dotenv
import requests

load_dotenv()

if (os.getenv("dev") == "local"):
    BLOB_READ_WRITE_TOKEN = os.getenv("BLOB_READ_WRITE_TOKEN")

else:
    BLOB_READ_WRITE_TOKEN = os.environ['BLOB_READ_WRITE_TOKEN']
    
def init_photos_to_blob(photos):

    #takes an array of photo urls and uses a threadpool to concurrently upload each to blob
    #returns an array of urls to the uploaded photos
    with ThreadPoolExecutor() as executor:
        results = executor.map(upload_photo_to_blob, photos)
    return list(results)

def upload_photo_to_blob(photoUrl):
    #uploads a photo to blob and returns the url
    file = requests.get(photoUrl)
    file_name = hashlib.md5(photoUrl.encode()).hexdigest()
    file_url = vercel_blob.put(file_name, file.content, {}).get('url')
    return file_url

def upload_file_to_blob(file):
    #uploads a file to blob and returns the url
    return (vercel_blob.put(file.filename, file.read(), {})).get('url')

def clear_blob():
    #clears the blob storage
    return vercel_blob.clear()