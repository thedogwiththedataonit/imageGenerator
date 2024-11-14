import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()
# Set your OpenAI API key
if (os.getenv("dev") == "local"):
    OPEN_AI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_ADMIN_ASSISTANT_MODEL_ID = os.getenv("OPENAI_ADMIN_ASSISTANT_MODEL_ID")
else:
    OPEN_AI_API_KEY = os.environ['OPENAI_API_KEY']
    OPENAI_ADMIN_ASSISTANT_MODEL_ID = os.environ['OPENAI_ADMIN_ASSISTANT_MODEL_ID']

client = OpenAI(api_key=OPEN_AI_API_KEY)

# we need to create example home objects based on a collection

collections_list = [
  'Apartments',
  'Homes',
  'Studios',
  'Beachfront',
  'Cabins',
  'Castles',
  'Tropical'
  'Camping',
  'Farms',
]

# for each collection, create 50 unique home examples


prompt = '''Each home object should have the following properties: "bnbId", "name", "rating", "guests", "features", "reviews", "price", "beds", "bedrooms", "bathrooms", "size", "location", and "description". Use the example provided as a guide to make sure each home object is unique. The description should be atleast 200 characters long. The bnbId should be a 12 character long hex random string. There should be atleast 5 features for each home object. The location should be a city in the United States. The size should be in square feet. The price should be in USD. The rating should be a float between 1 and 5. The reviews should be an integer. The guests, beds, bedrooms, and bathrooms should be integers.

            Do not include any explanations, only provide a RFC8259 compliant JSON response following this format without deviation. 
            [
            {"bnbId": "123hjkdw93hg", "name": "A snug little apartment", "rating": 4.5, "guests": 5, "features": ["Ocean view", "Wifi", "Kitchen", "Wash and Dry", "Security Cameras", "Free Parking"], "reviews": 10, "price": 100, "beds": 2, "bedrooms": 1, "bathrooms": 1, "size": "500 sqft", "location": "New York, NY", "description": "A cozy apartment in the heart of the city. Perfect for a weekend getaway. Close to all the best restaurants and shopping."},
            ...
            ]
            '''

def generateBNBObjects(collection, bnbCount):
  preprompt = "Create a json list of " + str(bnbCount) + "unique home objects for the collection: " + collection + ". The created JSON objects for each bnb home should be within the theme of the collection. Make intuitive examples."
  response = client.chat.completions.create(
    model="gpt-4-turbo",
    messages=[
      {
        "role": "user",
        "content": [
          {"type": "text", "text": preprompt + prompt},
        ],
      }
    ],
    max_tokens=4096, #max tokens is 600
  )
  chat_response = (response.choices[0])
  response = chat_response.message.content
  json_response = json.loads(response)
  print(json_response)
      
  return json_response

    
    
#generateBNBObjects("Apartments")
