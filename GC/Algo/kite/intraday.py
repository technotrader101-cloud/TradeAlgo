import requests
from kiteconnect import KiteConnect
from urllib.parse import urlparse, parse_qs
import pyotp
import credentials as cr

import logging


logging.basicConfig(level=logging.DEBUG)

kite = KiteConnect(api_key=cr.api_key)
print(kite.login_url()) 


