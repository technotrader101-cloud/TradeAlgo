import credentials as cr
from py5paisa import FivePaisaClient
from py5paisa.strategy import *
import pandas as pd
import time
import configparser
import warnings
from io import StringIO
import pyotp

# Example: Suppress all deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# masignalpath = "C:/Users/91915/Documents/aliceblue/masignal.ini"     
masignalpath = "masignal.ini"
config = configparser.ConfigParser()


#This function will automatically take care of generating and sending access token for all your API's
client = FivePaisaClient(cred=cr.cred)

totp = pyotp.TOTP(cr.totp_key)
current_otp = totp.now()

# New TOTP based authentication
client.get_totp_session(cr.clientId, current_otp, cr.pin)


def on_message(ws, message):  
    
    json_io = StringIO(message)

    data = pd.read_json(json_io)
    # print(data)
    # ltp = float(data['LastRate'])
    ltp = float(data.iloc[0, 3])
    config.read(masignalpath)
    print(ltp)
    if ltp < 30000:
        config['indexltp'] = {'indexspot' : ltp}

    if ltp > 30000 and ltp < 70000:
        config['bnfltp'] = {'bnfltp' : ltp}
    
    if ltp > 70000:
        config['sensex'] = {'sensex' : ltp}
    # if ltp > 19600 and ltp < 30000:
     #   config['finltp'] = {'finspot' : ltp}
    with open(masignalpath, 'w') as configfile:
        config.write(configfile)
    configfile.close()
        

def get_live_stream_ltp(scrip_code1,scrip_code2, scrip_code3):
# def get_live_stream_ltp(scrip_code1,scrip_code2, scrip_code3):
    # Define the request list to get live feed for the stock
    req_list = [
    {"Exch":"N","ExchType":"C","ScripCode": scrip_code1},
    {"Exch":"N","ExchType":"C","ScripCode": scrip_code2},
     {"Exch":"B","ExchType":"C","ScripCode": scrip_code3}


    ]
    # Request the live feed from the 5paisa server
    req_data = client.Request_Feed('mf', 's', req_list)
    
    # Subscribe to the live feed
    # client.connect(req_data)
    client.connect(req_data)
  

    
    client.receive_data(on_message)

while True:
    #BNF  999920005
    #Nifty 999920000
    #FNNIFTY : 999920041
    #Sensex : 999901
    get_live_stream_ltp (999920000,999920005, 999920041)
    time.sleep(2)
  
