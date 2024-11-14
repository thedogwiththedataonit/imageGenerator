#main init file

from api.util.mongo_functions import *
from api.util.openai_digraming import *
from api.util.getAI_functions import *
from api.util.blob_functions import *
from concurrent.futures import ThreadPoolExecutor


bnbCount = 20
imageCount = 5

def main():
    collection = "Apartments"
    json_response = generateBNBObjects(collection, bnbCount)
    
    for bnb in json_response:

        #use thread pool here to speed up the process to get images for each bnb['features'][i]
        image_prompts = []
        for i in range(imageCount):
            image_prompts.append("A beautiful " + collection + bnb['name'] + ". " + bnb['features'][i])
            
        with ThreadPoolExecutor() as executor:
            image_urls = (list(executor.map(create_image_from_prompt, image_prompts)))

        print(image_urls)
        blob_urls = init_photos_to_blob(image_urls)
        print(blob_urls)
        bnb['image_urls'] = blob_urls
        
    
    print(json_response)
    add_documents_to_collection(collection, json_response)
    
print("Starting")
main()