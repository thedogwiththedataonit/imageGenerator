
from pymongo import MongoClient, errors
import os
import sys
import certifi
from dotenv import load_dotenv

load_dotenv()

if (os.getenv("dev") == "local"):
    connection_string = os.getenv("MONGO_CONNECTION_STRING")
    database = os.getenv('MONGO_DB')
else:
    connection_string = os.environ['MONGO_CONNECTION_STRING']
    database = os.environ['MONGO_DB']
    

try:
  client = MongoClient(connection_string, tlsCAFile=certifi.where())
  
# return a friendly error if a URI error is thrown 
except errors.ConfigurationError:
  print("An Invalid URI host error was received. Is your Atlas host name correct in your connection string?")
  sys.exit(1)

db = client[database]

def test_connection():
    #tests the connection to the database
    try:
        client.server_info()
        print("Connected to MongoDB")
    except Exception as e:
        print("An error occurred: ", e)
        sys.exit(1)

def add_documents_to_collection(collection, documents):
    #adds a list of documents to a collection
    try:
        db[collection].insert_many(documents)
        print("Documents added to collection: " + collection)
    except Exception as e:
        print("An error occurred: ", e)
        sys.exit(1)

