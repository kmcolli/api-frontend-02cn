import requests, json, urllib, random, string, pika, ssl, os, logging, config, datetime
from flask import Flask, request
from flask_restful import Api, Resource
from config import Config
from logging.config import dictConfig
from logdna import LogDNAHandler
from subprocess import call, check_output, Popen, PIPE
from random import seed, gauss
from werkzeug import serving
from flask_cors import CORS

dictConfig({
            'version': 1,
            'formatters': {
                'default': {
                    'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
                }
            },
            'handlers': {
                'logdna': {
                    'level': logging.DEBUG,
                    'class': 'logging.handlers.LogDNAHandler',
                    'key': os.environ.get('LOGDNA_APIKEY'),
                    'options': {
                        'app': 'api-frontend-02cn.py',
                        'tags': os.environ.get('SERVERNAME'),
                        'env': os.environ.get('ENVIRONMENT'),
                        'url': os.environ.get('LOGDNA_LOGHOST'),
                        'index_meta': True,
                    },
                 },
            },
            'root': {
                'level': logging.DEBUG,
                'handlers': ['logdna']
            }
        })

HOST = '0.0.0.0'
PORT = 8000

app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})
app.logger.debug("Starting zero to cloud native api frontend")

app.config.from_object(Config)

api = Api(app)

def getRequestId():
    letters = string.ascii_uppercase
    return ''.join(random.choice(letters) for i in range(6))

def getiamtoken():
    iamhost=os.environ.get("UTILITY_02CN_SERVICE_SERVICE_HOST")
    iamport=os.environ.get("UTILITY_02CN_SERVICE_SERVICE_PORT")
    iam_url="http://"+iamhost+":"+iamport+"/api/v1/getiamtoken/"
    iam_data = { "apikey":  app.config["IBMCLOUD_APIKEY"]}
    headers = { "Content-Type": "application/json" }
    resp = requests.get(iam_url, data=json.dumps(iam_data), headers=headers)
    iamtoken = resp.json()["iamtoken"]
    return iamtoken    


def getRabbitCert(reqid, apikey):
    app.logger.debug("{} Starting to get RabbitMQ Certificate ")
    iamToken = getiamtoken()
    certManagerEndpoint = app.config['CERT_MANAGER_ENDPOINT']
    header = {
        'accept': 'application/json',
        'Authorization': 'Bearer ' + iamToken["access_token"]
    }
    rabbit_crn = app.config['RABBITMQ_CERT_CRN']
    url = certManagerEndpoint+'/api/v2/certificate/'+urllib.parse.quote_plus(rabbit_crn)
    response = requests.get(url,headers=header)
    json_response = json.loads(response.text)
    
    return json_response['data']['content']

def realtimemessage(queue, message):
    app.logger.debug("Starting real time message")
    try:

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.verify_mode = ssl.CERT_REQUIRED
        cert = getRabbitCert("REALTIME", app.config["IBMCLOUD_APIKEY"])
        context.load_verify_locations(cadata=cert)
        conn_params = pika.ConnectionParameters(port=app.config['RABBITMQ_PORT'],
                                            host=app.config['RABBITMQ_HOST'],
                                            credentials=pika.PlainCredentials(app.config['RABBITMQ_USER'],
                                                                              app.config['RABBITMQ_PASSWORD']),
                                            ssl_options=pika.SSLOptions(context))
        connection = pika.BlockingConnection(conn_params)
        message_queue = queue
        message_channel = connection.channel()
        message_channel.queue_declare(queue=queue, durable=True)
        message_channel.confirm_delivery()
        try:
            message_channel.basic_publish(exchange='', routing_key=message_queue, body=json.dumps(message),  properties=pika.BasicProperties(delivery_mode=2))
        except pika.exceptions.UnroutableError:
            connection.close()
    except Exception as e:
        connection.close()
    connection.close()

class EnableSSH(Resource):
    def post(self):
        try:
            input_json_data = request.get_json()
            reqid=getRequestId()
            app.logger.info("{} Zero to Cloud Native API Starting enable SSH.".format(reqid))
            apikey = input_json_data['apikey']
            clustername = input_json_data['cluster_name']

            message = { "reqid": reqid,
                        "action": "enableSSH",
                        "APIKEY": apikey,
                        "CLUSTER_NAME": clustername
                        }
            app.logger.debug("{} Sending real time message to enable SSH.".format(reqid))
            json_message = json.dumps(message)
            realtimemessage(app.config["RABBITMQ_QUEUE"], json_message ) 
            app.logger.info("{} Successfully requested enable SSH".format(reqid))    
            return {
                "Status":"Successfully requested enable SSH. Request id = "+reqid,
                "View Logs": "https://status.zero-to-cloud-native.com/?reqid="+reqid
            }
        except:
            app.logger.error("{} Problem requesting enable SSH".format(reqid))
            return {
                "Status":"Problem requesting enable SSH. Request ID = "+reqid,
                "View Logs": "https://status.zero-to-cloud-native.com/?reqid="+reqid
            }

class GetOCPToken(Resource):
    def post(self):
        try:
            input_json_data = request.get_json()
            reqid=getRequestId()
            app.logger.info("{} Zero to Cloud Native API Starting Get OCP Token.".format(reqid))
            apikey = input_json_data['apikey']
            clustername = input_json_data['cluster_name']
            
            headers = { "Content-Type": "application/json" }
            port = os.environ.get("OCP_REALTIME_02CN_SERVICE_SERVICE_PORT")
            url = "http://"+os.environ.get("OCP_REALTIME_02CN_SERVICE_SERVICE_HOST")
            openshift_realtime_url = url+":"+port+"/api/v1/getOCPToken/"
            data={ "reqid": reqid,
                   "apikey": apikey,
                   "clustername": clustername}
            response = requests.get(openshift_realtime_url,headers=headers,data=json.dumps(data))
            token = response.json()["token"]
            server = response.json()["server"]
            return { "Status": "Successfully got ocp token",
                     "token": token,
                     "login": "oc login --token="+token+" --server="+server,
                     "View Logs": "https://status.zero-to-cloud-native.com/?reqid="+reqid
                    }
        except Exception as e:
            app.logger.error("{} Zero to Cloud Native API Starting Get OCP token  {}".format(reqid, e))
            return {
                "Status":"Problem getting ocp token for request id "+reqid,
                "View Logs": "https://status.zero-to-cloud-native.com/?reqid="+reqid
            }

class GetOCPVersions(Resource):
    def get(self):
        try:
            reqid=getRequestId()
            app.logger.info("{} Zero to Cloud Native API Starting Get OCP Versions.".format(reqid))
            
            headers = { "Content-Type": "application/json" }
            port = os.environ.get("OCP_REALTIME_02CN_SERVICE_SERVICE_PORT")
            url = "http://"+os.environ.get("OCP_REALTIME_02CN_SERVICE_SERVICE_HOST")
            openshift_realtime_url = url+":"+port+"/api/v1/getOCPVersions/"
            data={ "reqid": reqid}
            response = requests.get(openshift_realtime_url,headers=headers,data=json.dumps(data))
            versions=response.json()
            app.logger.debug("{} Successfully got these ocp versions {}".format(reqid, versions)) 
            return { 
                "versions": versions,
                "View Logs": "https://status.zero-to-cloud-native.com/?reqid="+reqid
            }
        except Exception as e:
            app.logger.error("{} Error Zero to Cloud Native API getting OCP versions  {}".format(reqid, e))
            return {
                "Status":"Problem getting roks versions for request id "+reqid,
                "View Logs": "https://status.zero-to-cloud-native.com/?reqid="+reqid
            }


api.add_resource(EnableSSH, '/api/v1/enableSSH/')
api.add_resource(GetOCPToken, '/api/v1/getOCPToken/')
api.add_resource(GetOCPVersions, '/api/v1/getOCPVersions/')
getRabbitCert('START-API-FRONTEND ', app.config['IBMCLOUD_APIKEY'])

context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
context.load_cert_chain("/app/server.crt", "/app/server.key")
if __name__ == '__main__':
    app.run(host=HOST, port=PORT, threaded=True, debug=True, ssl_context=context)
    #app.run(host=HOST, port=PORT, threaded=True, debug=True)
