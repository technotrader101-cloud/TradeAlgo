import credentials as cr
#from py5paisa import FivePaisaClient
from py5paisa.strategy import *
from datetime import datetime, timedelta
import time
from time import sleep
from dateutil.tz import gettz

   
def next_thursday():
    """Return next Thursday YYYYMMDD, or Wednesday if Thursday is a holiday."""
    
    # Define holidays (modify this list as needed)
    holidays = {
        '20251002',  # Gandhi Jayanti
        '20251225',  # Christmas
        '20251031',  # Diwali
        '20251226',  # Boxing Day
        # Add more holidays as needed
    }
    
    today = datetime.now()
    days = 3 - today.weekday()  # Thursday is weekday 3
    if days <= 0:
        days += 7
    
    th = today + timedelta(days=days)
    
    # Check if Thursday is a holiday
    if th.strftime('%Y%m%d') in holidays:
        # Return Wednesday instead (one day earlier)
        wed = th - timedelta(days=1)
        return wed.strftime('%Y%m%d')
    
    return th.strftime('%Y%m%d')

Losslimit = -5000
try:
    while True:
        print(next_thursday())


except KeyboardInterrupt:
    #buy Straddle
    sleep(1)


print('program ended')
