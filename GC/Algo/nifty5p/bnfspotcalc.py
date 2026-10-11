import credentials as cr
from py5paisa import FivePaisaClient
from py5paisa.strategy import *
import pandas as pd
import time
import configparser
import warnings
from io import StringIO
import asyncio

# Example: Suppress all deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# masignalpath = "C:/Users/91915/Documents/aliceblue/masignal.ini"     
masignalpath = "masignal.ini"
config = configparser.ConfigParser()
client = FivePaisaClient(email=cr.email, passwd=cr.password, dob=cr.dob, cred=cr.cred)

client.login()


bank_nifty_constituents = [
    {'name': 'HDFCBank',  'scrip_code': 1333, 'weight': 32.88},

    # Add all desired constituents here
]

# Prepare request as required by py5paisa
# req_list = [{'Exch': 'N', 'ExchType': 'C', 'ScripCode': s['scrip_code']} for s in bank_nifty_constituents]
req_list = [{'Exch': 'N', 'ExchType': 'C', 'ScripCode': 1333 }]


# Use the correct method to fetch market data
market_data = client.fetch_market_feed(req_list)
print(market_data)

bank_nifty_spot = 0

for stock in bank_nifty_constituents:
    scrip = stock['scrip_code']

    data = market_data.get(scrip)
    if data:
        last_price = data.get('LastRate', 0)
        weight = stock['weight'] / 100
        contribution = last_price * weight
        bank_nifty_spot += contribution
        print(f"{stock['name']} ({scrip}): Spot={last_price}, Weight={stock['weight']}%, Contribution={contribution:.2f}")
    else:
        print(f"No market data for {stock['name']} ({scrip})")

print(f"\nEstimated Bank Nifty Spot: {bank_nifty_spot:.2f}")

