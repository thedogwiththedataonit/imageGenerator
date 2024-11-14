from ddtrace import tracer, patch_all, config
from flask import Flask, request, jsonify
from flask_cors import CORS
from api.util.mongo_functions import *
import os
from api.util.model import *
import time
import random
import hashlib
from functools import wraps
import json
from api.util.blob_functions import *
from api.util.datadog_logging import log_to_datadog
from api.util.graph_functions import create_graph_data
from api.util.openai_digraming import base64_image_to_nodes
from api.util.aws_functions import *
import jwt

from dotenv import load_dotenv
import requests as req
load_dotenv()

if os.getenv("dev") == "local":
    API_VERSION = os.getenv('API_VERSION')
    CLERK_PEM_PUBLIC_KEY = os.getenv('CLERK_PEM_PUBLIC_KEY')
    ADMIN_SITE = os.getenv('ADMIN_SITE')
    DATADOG_TESTING_VERIFY_PIN = os.getenv('DATADOG_TESTING_VERIFY_PIN')
    DATADOG_TESTING_EMAIL = os.getenv('DATADOG_TESTING_EMAIL')
    DD_APM_HOST = os.getenv('DD_APM_HOST')
    STORTRACK_INTEGRATIONS_ENDPOINT = os.getenv('STORTRACK_INTEGRATIONS_ENDPOINT')
else:
    API_VERSION = os.environ['API_VERSION']
    CLERK_PEM_PUBLIC_KEY = os.environ['CLERK_PEM_PUBLIC_KEY']
    ADMIN_SITE = os.environ['ADMIN_SITE']
    DATADOG_TESTING_VERIFY_PIN = os.environ['DATADOG_TESTING_VERIFY_PIN']
    DATADOG_TESTING_EMAIL = os.environ['DATADOG_TESTING_EMAIL']
    DD_APM_HOST = os.environ['DD_APM_HOST']
    STORTRACK_INTEGRATIONS_ENDPOINT = os.environ['STORTRACK_INTEGRATIONS_ENDPOINT']

CLERK_PEM_PUBLIC_KEY = '''-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvxb2ywE9Q+gzHc5dT72j
2Y74RJowJHrkXtzpsNF4BjysgNj6NSwdECoMgCxc9gSUen2reMh7z1SDYs28Tf9I
4KGg5NGbqOrP2vkURGlCElFvzu6xxwUNHBfCQNpDswZXjzempgnhp8tY/ht4zRl/
VxQVb0wrSItYhrvbCQPFUx//LM0T6JZnKBs9G1hP3drdjmgLep6zsdOuPPXgUpcT
0ZcO4QGLDUDmPqBxAlT5deQxR3/no0BCBy9tBzUK5DZ/y343Zuy2+EXkLi3ljFRS
Vl8Figk0Ysxb3du59x7FApDV8ZUsJ6ya4mNMiUZuIl/TFO28UL8pscdvInWTGTwp
MwIDAQAB
-----END PUBLIC KEY-----'''

config.env = "dev"      # the environment the application is in
config.service = "org"  # name of your application
config.version = "1"  # version of your application
patch_all()
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
pin_expiration = 3600 #1 hour
tracer.configure(hostname=DD_APM_HOST, port=8126)


def authenticate_bearer_token(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        span = tracer.current_span()
        correlation_ids = (str((1 << 64) - 1 & span.trace_id), span.span_id) if span else (None, None)
        trace_id, span_id = correlation_ids
        token = request.headers.get('Authorization')
        if not token or not token.startswith('Bearer '):
            return jsonify({'message': 'Missing or invalid Bearer token', "status":401})
        # Extract the token from the Authorization header
        token = token.split(' ')[1]

        # Perform token validation logic here (e.g., verify against database)
        try:
          jwt_object = jwt.decode(token, key=CLERK_PEM_PUBLIC_KEY, algorithms=['RS256'])
          log_to_datadog("Token validated", level="info", trace_id=(trace_id), span_id=(span_id), jwt=jwt_object)
          uid = jwt_object['uid']
          orgId = jwt_object['orgId'] if 'orgId' in jwt_object else False
          
        except Exception as e:
          log_to_datadog("Error validating token", level="error", error=str(e), trace_id=(trace_id), span_id=(span_id))
          return jsonify({'message': 'Error validating token', "status":401})
        if not uid:
            log_to_datadog("No uid", level="error", trace_id=(trace_id), span_id=(span_id))
            return jsonify({'message': 'Invalid token', "status":401})
        if uid:
            #pass the uid to the function
            return func(uid, orgId, *args, **kwargs)
        else:
            log_to_datadog("Invalid token", level="error", trace_id=(trace_id), span_id=(span_id))
            return jsonify({'message': 'Invalid token', "status":401})
    return wrapper

@app.route('/')
def home():
    span = tracer.current_span()
    correlation_ids = (str((1 << 64) - 1 & span.trace_id), span.span_id) if span else (None, None)
    trace_id, span_id = correlation_ids
    log_to_datadog("Home route hit", level="info", trace_id=(trace_id), span_id=(span_id))
    return 'Hello, World hehe'
    
@app.route(f'/api/{API_VERSION}/add_customer', methods=['POST'])
@authenticate_bearer_token
def add_customer(uid, orgId):
    span = tracer.current_span()
    correlation_ids = (str((1 << 64) - 1 & span.trace_id), span.span_id) if span else (None, None)
    trace_id, span_id = correlation_ids
    customer = request.json
    customer_dict = Customer(orgId=orgId, **customer)
    customerId = customer['customerId']
    customerName = customer['name']
    customerEmail = customer['email']
    phoneNumber = customer['phoneNumber']
    try:
      response = add_doc("customers", customer_dict.__dict__)
      notification = add_notification(f"{customerName}", f"{customerEmail}", "Added Customer", orgId=orgId, customerId=customerId, userId=customer['addedBy'])

      log_to_datadog(f"Customer {customerName} {customerEmail} added", level="info", customerId=customerId, orgId=orgId, customerName=customerName, customerEmail=customerEmail, phoneNumber=phoneNumber, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":response, "notification":notification})
    except Exception as e:
      log_to_datadog(f"Error adding customer {customerId}", level="error", error=str(e), customerId=customerId, orgId=orgId, customerName=customerName, customerEmail=customerEmail, phoneNumber=phoneNumber, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error adding customer", "error":e})
      
@app.route(f'/api/{API_VERSION}/org_details', methods=['GET'])
@authenticate_bearer_token
def org_details(uid, orgId):
    trace_id, span_id = traceId(tracer.current_span())
    try:
      userDoc = get_doc("users", uid)
      orgDoc = get_doc("orgs", orgId)
      log_to_datadog(f"Org details retrieved", level="info", orgId=orgId, userId=uid, email=userDoc['email'], trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"success", "org":orgDoc})
    except Exception as e:
      log_to_datadog(f"Error retrieving org details", level="error", error=str(e), orgId=orgId, userId=uid, email=userDoc['email'], trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error getting org details", "error":e})
    
@app.route(f'/api/{API_VERSION}/profile_details', methods=['GET'])
@authenticate_bearer_token
def profile_details(uid):
    trace_id, span_id = traceId(tracer.current_span())
    try:
      userDoc = get_doc("users", uid)
      log_to_datadog(f"Settings details retrieved", level="info", userId=uid, email=userDoc['email'], trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"success", "user":userDoc})
    except Exception as e:
      log_to_datadog(f"Error retrieving profile details", level="error", error=str(e), userId=uid, email=userDoc['email'], trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error getting profile details", "error":e})

    
@app.route(f'/api/{API_VERSION}/verify_facility/<id>', methods=['GET'])
@authenticate_bearer_token
def verify_facility(uid, id):
    trace_id, span_id = traceId(tracer.current_span())
    facilityId = id

    try:
      facility = get_doc("facilities", facilityId)
      orgId = facility['orgId']
      check_uid = check_uid_in_org(orgId, uid)
      if not check_uid:
        log_to_datadog(f"Error verifying facility {facilityId}", level="error", error=f"User {uid} does not have permission to verify facility {facilityId}", facilityId=facilityId, orgId=orgId, trace_id=trace_id, span_id=span_id)
        return jsonify({"data":f"User does not have permission to verify facility {facilityId}"})

      if facility:
        response = update_doc("facilities", facilityId, {"verified":True})
        notification = add_notification(f"Verification pending for {facility['facilityName']}", f"{facility['fullAddress']}", "Verification Requested", orgId=orgId, facilityId=facilityId, userId=uid)
        log_to_datadog(f"Facility {facilityId} verified", level="info", facilityId=facilityId, orgId=orgId, trace_id=trace_id, span_id=span_id)
        return jsonify({"data":response, "notification":notification})
      else:
        log_to_datadog(f"Error verifying facility {facilityId}", level="error", error=f"Facility {facilityId} does not exist", facilityId=facilityId, orgId=orgId, trace_id=trace_id, span_id=span_id)
        return jsonify({"data":f"Facility {facilityId} does not exist"})
    except Exception as e:
      log_to_datadog(f"Error verifying facility {facilityId}", level="error", error=str(e), facilityId=facilityId, orgId=orgId, trace_id=trace_id, span_id=span_id)
      return jsonify({"data":"Error verifying facility", "error":e})
  
@app.route(f'/api/{API_VERSION}/iot_lock_activity', methods=['POST'])
def iot_lock_activity():
    trace_id, span_id = traceId(tracer.current_span())
    data = request.json
    data = data['mqtt']
    log_to_datadog("Recieved lock activity", level="info", data=data, trace_id=trace_id, span_id=span_id)
    #get the lock activity
    #parse it out and add as an activity
    
    #subject
    #eventType
    #lockId
    #orgId
    #pinUsed [1,2,3,4,5,6]
    #pinType: "user"
    #battery
    #timestamp in seconds
    #status locked
    try:
      eventType = data['eventType']
      battery = data['battery']
      pinUsed = ""
      pinType = data['pinType']
      status = data['status']
      
      
      
      if (eventType == "unlockSuccess"):
        message = "Lock unlock successful."
      elif (eventType == "unlockFailed"):
        pinUsed = data['pinUsed'] 
        #pin used is array of numbers, combine into string
        pinUsed = ''.join(map(str, pinUsed))
        message = f"Lock unlock failed. The incorrect pin was entered ({pinUsed})"
      elif (eventType == "pinCreated"):
        message = "Pin created."
      elif (eventType == "pinDeleted"):
        message = "Pin deleted."
      elif (eventType == "pinExpired"):
        message = "Pin expired."
      elif (eventType == "unlockFailed"):
        message = "Lock unlock failed."
      elif (eventType == "lowPowerShutdown"):
        message = "Lock low power shutdown."
      elif (eventType == "alarm"):
        message = "Lock alarm."
      elif (eventType == "statusUpdate"):
        message = "Lock status update."
      elif (eventType == "readyToOpen"):
        #grab the pinUsed
        pinUsed = data['pinUsed'] 
        #pin used is array of numbers, combine into string
        pinUsed = ''.join(map(str, pinUsed))
        message = f"The correct pin was entered ({pinUsed}). Lock is ready to open."
      elif (eventType == "wakeUp"):
        message = "Lock woke up from napping..."
      elif (eventType == "locked"):
        message = "Lock locked."
      elif (eventType == "lowPowerShutdown"):
        message = "Lock low power shutdown."
        
        
      
      #update lock battery percentage
      update_doc("locks", data['lockId'], {"batteryPercentage":battery})
      #get orgId of demo@gogridlock.com
      demoOrg = search_by_email("demo@gogridlock.com")
      if (demoOrg == False):
        return jsonify({"status":"demo org not found"})
      #create activity
      orgId = demoOrg['orgId']
      
       #hash of timestamp and lockId
      activityId = hashlib.sha256((str(data['timestamp']) + data['lockId']).encode()).hexdigest()
      activity = Activity(activityId=activityId, customerId="demo", eventType=eventType, 
                          message=message, timestamp=data['timestamp'], orgId=orgId, 
                          facilityId="demo", floorId="demo", unitId="demo",
                          lockId=data['lockId'], userId="demo", pinId=pinUsed, rentalAgreementId="demo")
      sse_activity = activity.__dict__
      del sse_activity["_id"]
      response = add_doc("activity", activity.__dict__)
      
      publish_message(orgId, sse_activity)  
      log_to_datadog(f"Lock activity added", level="info", activityId=activity.activityId, eventType=activity.eventType, message=activity.message, timestamp=activity.timestamp, orgId=activity.orgId, lockId=activity.lockId, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"success", "data":response})
    except Exception as e:
      log_to_datadog("Error adding lock activity", level="error", error=str(e), trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error adding lock activity", "error":str(e)})


@app.route(f'/api/{API_VERSION}/graph/<startTime>/<endTime>/<resource>/<query>', methods=['GET'])
@authenticate_bearer_token
def graph_widget(uid, orgId, startTime, endTime, resource, query):
    trace_id, span_id = traceId(tracer.current_span())
    #query is query?param=value&param2=value2
    #turn into a dictionary
    
    #check if query does not exist
    #query = key1=value1&key2=value2
    startTime = int(startTime)
    endTime = int(endTime)
    if (query == "null"):
      query = {}
    else:
      query = dict(parse_qsl(query))
    try:
      if (resource == "get_activity_graph"):
        collection = "activity"
        document_key = 'eventType'
        
      elif (resource == "get_activity_graph_by_facility"):
        collection = "activity"
        document_key = 'facilityName'  
        
      elif (resource == "get_checkouts_graph"):
        collection = "payments"
        document_key = 'amount'
        
        pass
      elif (resource == "get_lease_days_graph"):
        collection = "rentalAgreements"
        document_key = "totalDays"
        
      elif (resource == "get_users_graph"):
        pass
      elif (resource == "get_purchases_graph"):
        pass
      elif (resource == "get_lease_durations_graph"):
        pass
      elif (resource == "get_unit_types_graph"):
        pass
      elif (resource == "get_unit_sizes_graph"):
        pass
      elif (resource == "get_unit_statuses_graph"):
        pass
      else:
        log_to_datadog(f"Error getting graph data", level="error", orgId=orgId, error=f"Resource {resource} not found", trace_id=trace_id, span_id=span_id)
        return jsonify({"status":f"Resource {resource} not found"})
      
      data = get_graph_data(collection, orgId, startTime, endTime, query)
      if (len(data) == 0):
        return jsonify({"status":"No data found", "data":data})
      if (resource == "get_activity_graph_by_facility"):
        data = add_additional_metadata(data, "facilityId", "facilityName", "facilities")
        pass
      
      graph_data = create_graph_data(data, startTime, endTime, document_key)
      
      return jsonify({"status":"success", "data":graph_data})
    except Exception as e:
      log_to_datadog(f"Error getting graph data", level="error", orgId=orgId, error=str(e), trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error getting graph data", "error":e})
    
@app.route(f'/api/{API_VERSION}/query_ids', methods=['POST'])
@authenticate_bearer_token
def query_ids(uid, orgId):
    trace_id, span_id = traceId(tracer.current_span())
    data = request.json
    key = data["key"]
    if (key == "activityId"):
      collection = "activity"
    ids = data['ids']
    
    try:
      docs = get_docs_by_ids(collection, key, ids)
      return jsonify({"status":"success", "docs":docs})
    except Exception as e:
      log_to_datadog(f"Error querying ids", level="error", orgId=orgId, error=str(e), trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error querying ids", "error":e})

@app.route(f'/api/{API_VERSION}/get_facility_floors', methods=['POST'])
@authenticate_bearer_token
def get_facility_floors(uid, orgId):
    trace_id, span_id = traceId(tracer.current_span())
    data = request.json
    facilityId = data['facilityId']
    try:
      floors = get_floors_by_facilityId(facilityId)
      #go through floors and change floor to label and floorId to value, remove all other keys and values
      for floor in floors:
        floor['label'] = floor['floorName']
        floor['value'] = floor['floorId']
        del floor['floorName']
        del floor['floor']
        del floor['floorId']
        del floor['facilityId'] 
        del floor['orgId']
      log_to_datadog(f"Facility floors retrieved", level="info", orgId=orgId, facilityId=facilityId, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"success", "floors":floors})
    except Exception as e:
      log_to_datadog(f"Error getting facility floors", level="error", orgId=orgId, error=str(e), trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error getting facility floors", "error":e})

@app.route(f'/api/{API_VERSION}/diagram', methods=['POST'])
@authenticate_bearer_token
def submit_diagram(uid, orgId):
    trace_id, span_id = traceId(tracer.current_span())
    diagram = request.json
  
    try:
      response = add_doc("diagrams", {"orgId":orgId, "diagram":diagram})
      log_to_datadog(f"Diagram submitted", level="info", orgId=orgId, diagram=diagram, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":response})
    except Exception as e:
      log_to_datadog(f"Error submitting diagram", level="error", error=str(e), trace_id=trace_id, orgId=orgId, span_id=span_id)
      return jsonify({"status":"Error submitting diagram", "error":e})
    
@app.route(f'/api/{API_VERSION}/diagram', methods=['GET'])
@authenticate_bearer_token
def fetch_diagram(uid, orgId):
    trace_id, span_id = traceId(tracer.current_span())
    try:
      response = get_doc("diagrams", orgId)
      if response == False:
        facilities = get_multiple_docs_by_orgId("facilities", orgId)
        units = get_multiple_docs_by_orgId("units", orgId)
        floors = get_multiple_docs_by_orgId("floors", orgId)
        
        if (len(facilities) == 0):
          return jsonify({"status":"No facilities found for diagram"})
        
        else:
          return jsonify({"status":"No diagram found", "facilities":facilities, "units":units, "floors":floors})
      else: #diagram exists
        facilities = get_multiple_docs_by_orgId("facilities", orgId)
        log_to_datadog(f"Diagram fetched", level="info", trace_id=trace_id, span_id=span_id, orgId=orgId)
        return jsonify({"status":"success", "nodes":response['diagram'], "facilities":facilities})
    except Exception as e:
      log_to_datadog(f"Error getting diagram", level="error", error=str(e), trace_id=trace_id, orgId=orgId, span_id=span_id)
      return jsonify({"status":"Error getting diagram", "error":e})


#MAIN PAGE COMPONENT QUERY
@app.route(f'/api/{API_VERSION}/<data_type>', methods=['GET'])
@authenticate_bearer_token
def query_data(uid, orgId, data_type):
  print(uid, orgId, data_type)
  trace_id, span_id = traceId(tracer.current_span())
  #units, facilities, floors, activities
  try:
    if (data_type == "subdomains"):
      response = get_all_subdomains()
      log_to_datadog(f"Subdomains retrieved", level="info", orgId=orgId, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"success", "data":response})
    
    if (data_type == "account"):
      user = get_doc("users", uid)
      org = get_doc("orgs", orgId)
      
      log_to_datadog(f"Account retrieved", level="info", orgId=orgId, trace_id=trace_id, span_id=span_id, user=user, org=org)
      return jsonify({"status":"success", "data":{"user":user, "org":org}})
    
    response = get_multiple_docs_by_orgId(data_type, orgId)
    log_to_datadog(f"{data_type} retrieved", level="info", orgId=orgId, userId=uid, trace_id=trace_id, span_id=span_id)
    return jsonify({"status":"success", "data":response})
  except Exception as e:
    log_to_datadog(f"Error getting {data_type}", level="error", error=str(e), trace_id=trace_id, span_id=span_id, orgId=orgId, userId=uid, response=response)
    return jsonify({"status":False, "error":str(e)})

@app.route(f'/api/{API_VERSION}/mutate/<data_type>', methods=['POST'])
@authenticate_bearer_token
def mutate_data(uid, orgId, data_type):
    trace_id, span_id = traceId(tracer.current_span())
  
    
    if (data_type == "facilities"):
      
      facility = request.json
      facilityId = facility['facilityId']
      facilityName = facility['facilityName']
      fullAddress = facility['fullAddress']
      address = facility['address']
      city = facility['city']
      state = facility['state']
      floors = facility['floors']

      #make facility['photos'] an array of urls of max 5 photos
      if (len(facility['photos']) > 5):
        facility['photos'] = facility['photos'][:5]
      
      stortrack_endpoint = f'{STORTRACK_INTEGRATIONS_ENDPOINT}/api/{API_VERSION}/stortrack/get_facility_info'
      try:
        #make an api request to the integrations function to get the storeId and masterId
        stortrack_facility_info = req.post(stortrack_endpoint, json={"radius":1,"lat": facility['latitude'],"lng": facility['longitude'],"address":address})
        #if the storetrack info is not 200,
        print(stortrack_facility_info.status_code)
        if (stortrack_facility_info.status_code != 200):
          log_to_datadog(f"Error getting storetrack facility info", level="error", error=stortrack_facility_info.json(), trace_id=trace_id, orgId=orgId, span_id=span_id)
          stortrack_facility_info = {"storeId":None, "masterId":None, "storeStatus":None}
          
        else:
          stortrack_facility_info = stortrack_facility_info.json()
          
          
          
        if (len(facility['photos']) > 0):
          facility['photos'] = init_photos_to_blob(facility['photos'])
          facility['focusPhoto'] = facility['photos'][0]
          log_to_datadog(f"Adding facility images to vercel blob", level="info", facilityId=facility["facilityId"], trace_id=trace_id, orgId=orgId, span_id=span_id, imgUrls=facility['photos'] )
        else:
          facility['photos'] = []
          facility['focusPhoto'] = None
          log_to_datadog(f"No facility images for {facility['facilityName']}", level="info", facilityId=facility["facilityId"], trace_id=trace_id, orgId=orgId, span_id=span_id )

          
        facilities_dict = Facility(orgId=orgId, storeId=stortrack_facility_info['storeId'], masterId=stortrack_facility_info['masterId'], storeStatus=stortrack_facility_info['storeStatus'], **facility)
        
        response = add_doc("facilities", facilities_dict.__dict__)
        create_floors(floors, facilityId, orgId)
        notification = add_notification(f"{facility['facilityName']}", f"{fullAddress}", "Added Facility", orgId=orgId, facilityId=facilityId, userId=uid)

        log_to_datadog(f"Facility {facilityId} added", level="info", facilityId=facilityId, orgId=orgId, facilityName=facilityName, fullAddress=fullAddress, address=address, city=city, state=state, trace_id=trace_id, span_id=span_id, response=response)
        return jsonify({"status":response, "notification":notification})
      except Exception as e:
        log_to_datadog(f"Error adding facility {facilityId}", level="error", error=str(e), facilityId=facilityId, orgId=orgId, facilityName=facilityName, fullAddress=fullAddress, address=address, city=city, state=state, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":"Error adding facilities and units", "error":e})

    elif (data_type == "units"):
      data = request.json
      userDoc = get_doc("users", uid)
      #check if units['upload'] exists and if its true
      unitsArray = data['unitArray']
      unitNodes = data['unitNodes']
      facilityId = data['facilityId']
      floorId = data['floorId']
      promo = data.get('promo', None)
      
      #check if this promotionTitle already exists for this facilityId
      if (promo):
        promotionId = check_promotion_exists(facilityId, promo)
        if (promotionId == False):
          log_to_datadog(f"New promotion for "+facilityId, level="error", error=f"Promotion {promo} doest exist for facility {facilityId}", facilityId=facilityId, orgId=orgId, userId=uid, trace_id=trace_id, span_id=span_id)
          promotionId = hashlib.sha256((str(time.time()) + promo).encode()).hexdigest()
          promotion = Promotion(orgId=orgId, promotionTitle=promo, promotionDescription=promo, promotionId=promotionId)
          add_doc("promotions", promotion.__dict__)
      else:
        promotionId = None
        
      w = data.get('w', None)
      h = data.get('h', None)
        
      org_added_units = []
      for unit in unitsArray:
        unit_dict = Unit(orgId=orgId, promotionId=promotionId, **unit)
        org_added_units.append(unit_dict.__dict__)
      units_response = add_doc("units", org_added_units)
      nodes_response = addUnitsToDiagram(unitNodes, orgId, facilityId, floorId, w, h)
        
      notification = add_notification((str(len(org_added_units))+" Units"), "Added via upload", "Added Units", orgId=orgId, floorId=floorId, facilityId=facilityId, userId=uid)
      log_to_datadog(f"Units added via upload", level="info", orgId=orgId, floorId=floorId, facilityId=facilityId, unitCount=len(org_added_units), userId=uid, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":units_response, "notification":notification})
    
    elif (data_type == "siteDetails"):
      
      data = request.json
      data['subdomain'] = to_lowercase(data['subdomain'])
      subdomain = data['subdomain']

      try:
        userDoc = get_doc("users", uid)
        facilityDoc = get_doc("facilities", data['facilityId'])
        
        if (facilityDoc['subdomain'] == None):
          subdomain_update = update_doc("facilities", data['facilityId'], {"subdomain":subdomain})
          response = update_doc("facilities", data['facilityId'], {"siteDetails":data})
          #add to vercel and aws
          aws_route_53_response = create_subdomain(subdomain)
          vercel_response = add_domain_to_vercel(subdomain)
          if ((aws_route_53_response == None) or (vercel_response == None)):
            #roll back changes
            update_doc("facilities", data['facilityId'], {"subdomain":None})
            update_doc("facilities", data['facilityId'], {"siteDetails":None})
            remove_subdomain(subdomain)
            remove_domain_from_vercel(subdomain)
            log_to_datadog(f"Error creating subdomain", level="error", error="Error creating subdomain", orgId=orgId, userId=uid, trace_id=trace_id, span_id=span_id)
            return jsonify({"status":"Error creating subdomain"})
          
          log_to_datadog(f"Site details updated", level="info", orgId=orgId, userId=uid, trace_id=trace_id, span_id=span_id)
          return jsonify({"status":response})
        
        else: #subdomain already exists
          #check if the subdomain is changed
          if (facilityDoc['subdomain'] != subdomain):
            #update subdomain
            subdomain_update = update_doc("facilities", data['facilityId'], {"subdomain":subdomain})
            #update site details
            response = update_doc("facilities", data['facilityId'], {"siteDetails":data})
            #update vercel and aws
            update_status = update_subdomain(old_subdomain=facilityDoc['subdomain'], new_subdomain=subdomain)
            if (update_status == "error"):
              log_to_datadog(f"Error updating subdomain", level="error", error="Error updating subdomain", orgId=orgId, userId=uid, trace_id=trace_id, span_id=span_id)
              return jsonify({"status":"Error updating subdomain"})
          
          else:
            response = update_doc("facilities", data['facilityId'], {"siteDetails":data})
            
          log_to_datadog(f"Site details updated", level="info", orgId=orgId, userId=uid, trace_id=trace_id, span_id=span_id)
          return jsonify({"status":response})
        
      except Exception as e:
        log_to_datadog(f"Error updating site details", level="error", error=str(e), orgId=orgId, userId=uid, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":"Error updating site details", "error":e})
      
    elif (data_type == "promotions"):
      data = request.json
      try:
        userDoc = get_doc("users", uid)
        promotionData = data['promotion']
        unitIds = data['unitIds']
        promotionId = hashlib.sha256((str(time.time()) + promotionData['promotionTitle']).encode()).hexdigest()
        promotion = Promotion(orgId=orgId, promotionId=promotionId, **promotionData)
        response = add_doc("promotions", promotion.__dict__)
        update_units_with_promotionId(unitIds, promotionId)
        notification = add_notification(f"{promotionData['promotionTitle']}", f"{promotionData['promotionDescription']}", "Added Promotion", orgId=orgId, userId=uid, unitIds=unitIds)
        log_to_datadog(f"Promotion {promotionId} added", level="info", orgId=orgId, promotionId=promotionId, promotionTitle=promotionData['promotionTitle'], promotionDescription=promotionData['promotionDescription'], userId=uid, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":response, "notification":notification})
      except Exception as e:
        log_to_datadog(f"Error adding promotion", level="error", error=str(e), orgId=orgId, userId=uid, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":"Error adding promotion", "error":e})
      
      
      
  #the gridlockQuery

@app.route(f'/api/{API_VERSION}/<data_type>/<id>', methods=['GET'])
@authenticate_bearer_token
def query_doc(uid, orgId, data_type, id):
    trace_id, span_id = traceId(tracer.current_span())
    #this is beautiful
    try:
      doc = get_doc(data_type, id)
      if (doc == False):
        log_to_datadog(f"Error getting {data_type} {id}", level="error", error=f"{data_type} {id} does not exist", orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":f"{data_type} {id} does not exist"})
      if (doc['orgId'] != get_doc("users", uid)['orgId']):
        log_to_datadog(f"Error getting {data_type} {id}", level="error", error=f"User {uid} does not have permission to view {data_type} {id}", orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":f"User does not have permission to view {data_type} {id}"})
      
      if (data_type == "activity"):
        doc = enrich_activity(doc)
      
      log_to_datadog(f"{data_type} {id} retrieved", level="info", orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"success", "data":doc})
    except Exception as e:
      log_to_datadog(f"Error getting {data_type} {id}", level="error", error=str(e), orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error getting {data_type} {id}", "error":e})
    
    
@app.route(f'/api/{API_VERSION}/delete/<data_type>/<id>', methods=['POST'])
@authenticate_bearer_token
def delete(uid, orgId, data_type, id):
  
    #if id has a comma, we are deleting multiple docs
    trace_id, span_id = traceId(tracer.current_span())
    try:
      if ("," in id):
        ids = id.split(",")
        for id in ids:
          doc = get_doc(data_type, id)
          orgId = doc['orgId']
          if (doc == False):
            log_to_datadog(f"Error deleting {data_type} {id}", level="error", error=f"{data_type} {id} does not exist", orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
            return jsonify({"status":"error", "message":"Does not exist!"})
          else:
            response = delete_doc(data_type, id, orgId)
          log_to_datadog(f"{data_type} {id} deletion => {response}", level="info", orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":response})
      else:
        doc = get_doc(data_type, id)
        if (doc == False):
          log_to_datadog(f"Error deleting {data_type} {id}", level="error", error=f"{data_type} {id} does not exist", orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
          return jsonify({"status":"error", "message":"Does not exist!"})

        response = delete_doc(data_type, id, doc['orgId'])
        log_to_datadog(f"{data_type} {id} deletion => {response}", level="info", doc_id=id, orgId=orgId, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":response})
    except Exception as e:
      log_to_datadog(f"Error deleting {data_type} {id}", level="error", error=str(e), doc_id=id, orgId=orgId, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error deleting {data_type} {id}", "error":e})


@app.route(f'/api/{API_VERSION}/details/<data_type>/<id>', methods=['GET'])
@authenticate_bearer_token
def details(uid, orgId, data_type, id):
    trace_id, span_id = traceId(tracer.current_span())
    try:
      doc = get_doc(data_type, id)
      if (data_type == "units"):
        #we have the doc, we need the facility and floor
        facility = get_doc("facilities", doc['facilityId'])
        floor = get_doc("floors", doc['floorId'])
        promotion = get_doc("promotions", doc['promotionId'])
        doc['facilityName'] = facility['facilityName']
        doc['floorName'] = floor['floorName']
        doc['fullAddress'] = facility['fullAddress']
        doc['address'] = facility['address']
        doc['city'] = facility['city']
        doc['state'] = facility['state']
        doc['zip'] = facility['zip']
        doc['longitude'] = facility['longitude']
        doc['latitude'] = facility['latitude']
        doc['promotion'] = promotion

      log_to_datadog(f"{data_type} {id} details retrieved", level="info",orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"success", "data":doc})
    except Exception as e:
      log_to_datadog(f"Error getting details {data_type} {id}", level="error",orgId=orgId, error=str(e), doc_id=id, trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error getting details {data_type} {id}", "error":e})

@app.route(f'/api/{API_VERSION}/update/<data_type>/<id>', methods=['POST'])
@authenticate_bearer_token
def update(uid, orgId, data_type, id):
    trace_id, span_id = traceId(tracer.current_span())
    
    if (data_type == "unit"):
      #we fit the json data into a unit object
      unit = request.json
      try:
        response = update_existing_fields("units", id, unit)
        log_to_datadog(f"Unit {id} updated", level="info", orgId=orgId, doc_id=id, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":response})
      except Exception as e:
        log_to_datadog(f"Error updating unit {id}", level="error", orgId=orgId, error=str(e), doc_id=id, trace_id=trace_id, span_id=span_id)
        return jsonify({"status":"Error updating unit", "error":e})
      
      
@app.route(f'/api/{API_VERSION}/upload/floor_units', methods=['POST'])
@authenticate_bearer_token
def upload_floor_units(uid, orgId):
    trace_id, span_id = traceId(tracer.current_span())
    base64_string = request.json['image']
    try:
      node_json = base64_image_to_nodes(base64_string)
      #we need to store in s3
      log_to_datadog(f"Floor units uploaded", level="info", userId=uid, orgId=orgId, trace_id=trace_id, span_id=span_id, node_json=node_json)
      return jsonify({"status":"success", "data":node_json})
    
    except Exception as e:
      log_to_datadog(f"Error uploading floor units", level="error",userId=uid, orgId=orgId,  error=str(e), trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error uploading floor units", "error":e})
    
@app.route(f'/api/{API_VERSION}/uploadfile', methods=['POST'])
@authenticate_bearer_token
def upload_file():
    trace_id, span_id = traceId(tracer.current_span())
    try:
      '''
        Client sends:
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('type', type);
        formData.append('typeId', typeId);
        '''
      file = request.files.get('file')
      file_type = request.form['type']
      file_typeId = request.form['typeId']
      print(file)
      print(file_type, file_typeId)
      
      img_url = upload_file_to_blob(file)
      #update the relevant type with the img_url
      
      if (file_type == "facility"):
        response = update_facility_images(file_typeId, img_url)
        if (response == False):
          return jsonify({"status":"Error updating facility image"})
      
      log_to_datadog(f"File uploaded", level="info", trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"success"})
    except Exception as e:
      log_to_datadog(f"Error uploading file", level="error", error=str(e), trace_id=trace_id, span_id=span_id)
      return jsonify({"status":"Error uploading file", "error":e})
    
@app.route(f'/api/{API_VERSION}/customersite', methods=['POST'])
@authenticate_bearer_token
def customer_site():
    trace_id, span_id = traceId(tracer.current_span())
    return jsonify({"status":"success"})
    
    #get the siteDetail object form the post
    #check if the siteDetail object exists
      
  
#what data does the home page need?
#facility count
#unit count
#percentage of status true (available)
#users count
#unit types count
#unit prices + avg market rates
#current dollar per sqft

#each graph is going to have its own api call and key, the key is graphkey+graphType+timeframe



#types of graphs




#maybe we need a separate api for the geoData


#subject: createPin
#lockId
#
def parse_qsl(query):
    return [(k, v) for k, v in (x.split('=') for x in query.split('&'))]
  
def get_seconds_from_timeframe(timeframe):
  #given the timeframe code, return the number of seconds in that timeframe
  if (timeframe == "30m"):
    return 1800
  
  elif (timeframe == "1hr"):
    return 3600
  
  elif (timeframe == "6hrs"):
    return 21600
  
  elif (timeframe == "12hrs"):
    return 43200
  
  elif (timeframe == "24hrs"):
    return 86400
  
  elif (timeframe == "1w"):
    return 604800
  
  elif (timeframe == "1m"):
    return 2592000
  
  elif (timeframe == "2m"):
    return 5184000
  
  elif (timeframe == "3m"):
    return 7776000

  elif (timeframe == "6m"):
    return 15552000
  
  elif (timeframe == "1y"):
    return 31536000
  
  else:
    return 86400

def to_lowercase(input_data):
    if isinstance(input_data, str):
        return input_data.lower()
    elif isinstance(input_data, list):
        return [to_lowercase(item) for item in input_data]
    elif isinstance(input_data, dict):
        return {key: to_lowercase(value) for key, value in input_data.items()}
    else:
        return input_data
      
def traceId(span):
  correlation_ids = (str((1 << 64) - 1 & span.trace_id), span.span_id) if span else (None, None)
  return correlation_ids
