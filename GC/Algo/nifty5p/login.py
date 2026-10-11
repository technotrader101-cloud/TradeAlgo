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

print(client.positions())