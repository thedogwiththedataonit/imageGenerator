#functions to create image based on prompt
import requests
from dotenv import load_dotenv
import time
import os
load_dotenv()
# Set your OpenAI API key
if (os.getenv("dev") == "local"):
    GETIMG_AI_API_KEY = os.getenv("GETIMG_AI_API_KEY")
else:
    GETIMG_AI_API_KEY = os.environ['GETIMG_AI_API_KEY']

def create_image_from_prompt(prompt):
    url = "https://api.getimg.ai/v1/flux-schnell/text-to-image"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + GETIMG_AI_API_KEY
    }
    data = {
        "prompt": prompt,
        "negative_prompt": "blurry",
        "width": 1024,
        "height": 1024,
        "response_format": "url"
    }
    
    response = requests.post(url, headers=headers, json=data)
    print(response.json())
    return response.json()['url']

#create_image_from_prompt("A beautiful sunset over the ocean")
