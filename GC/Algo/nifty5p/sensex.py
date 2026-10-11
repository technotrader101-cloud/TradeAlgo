# sensex_otm_options_strategy.py

'''
Sensex OTM Options Strategy: Step-by-Step Logic
	1.	Startup & Initialization
        •	Suppress unwanted “Success” prints from the 5paisa client.
        •	Read configuration (target premium, tolerance, symbol, quantity).
        •	Authenticate with the 5Paisa API.
	2.	Determine ATM Strike & Expiry
        •	Fetch the latest Sensex spot from your config file and round to the nearest ₹100 to get the ATM strike.
        •	Calculate the next expiry’s expiry date.
	3.	Scan for OTM Options Near ₹80 Premium
        •	Generate a list of out-of-the-money CE and PE strikes around the ATM (±15 steps of ₹100).
        •	For each strike, fetch the current premium.
        •	Collect only those strikes whose premium is within ₹80±₹10.
        •	From these, choose the single CE and single PE whose premiums are closest to ₹80.
	4.	Schedule Three “Sell Strangle” Entries
        •	At 9:45 AM, sell the chosen CE and PE (one lot each) as the first strangle.
        •	Record the traded prices, calculate SL at 1.2× traded price, and save the strike/scrip details.
        •	Repeat the process at 10:45 AM and again at 11:45 AM, each time scanning fresh strikes.
	5.	Continuous SL Monitoring & Exit
        •	Every 30–60 seconds, check each active position’s current premium.
        •	If any leg’s price rises to or above its SL level, exit (buy back) that leg and mark it “exited.”
	6.	Re-entry on Premium Drop
        •	For any leg that was exited, watch its original strike/scrip.
        •	If its premium falls back to ₹80 or below, re-sell that same leg and reset its SL at 1.2× the new traded price.
	7.	Real-time P&L Check
        •	Periodically compute intraday P&L for all Sensex positions.
        •	If P&L per lot breaches a predefined loss limit, exit all remaining positions immediately.
	8.	End-of-Day Cleanup
        •	At 2:45 PM, or if the loss limit is hit, exit any open legs.
        •	Log final trade details to Google Sheets.
        •	Reset internal flags and stop the program.
This workflow ensures you sell three fresh strangles during the morning, strictly manage risk with automatic stop-loss exits and re-entries, monitor overall profitability, and close all positions before market close.
'''

import sys

class FilteredWriter:
    def __init__(self, orig):
        self.orig = orig
    def write(self, data):
        # Drop any line that contains "Success"
        if "Success" in data:
            return
        self.orig.write(data)
    def flush(self):
        self.orig.flush()

# Replace stdout with the filter
sys.stdout = FilteredWriter(sys.stdout)

import credentials as cr
from py5paisa import FivePaisaClient
from datetime import datetime, timedelta
import configparser
from dateutil.tz import gettz
from time import sleep
import GsheetLog  
import pyotp

# Configuration
TARGET_PREMIUM = 90       # ₹80
tradePremium = 90

symbol = "SENSEX"
qty =20
# if datetime.today().weekday() == 3:  # 0=Monday ... 3=expiry
#     print("Today is expiry, adjusting target premium to ₹50")
#     tradePremium = 60
#     TARGET_PREMIUM = 60

PREMIUM_TOLERANCE = TARGET_PREMIUM * .12    # ±₹10

# Global position tracking and control variables
positions = {
    'trade1': {'ce_active': False, 'pe_active': False, 'ce_exited': False, 'pe_exited': False,
               'ce_scrip': None, 'pe_scrip': None, 'ce_strike': None, 'pe_strike': None,'ce_sl': 0, 'pe_sl': 0,
               'ce_traded_price': 0, 'pe_traded_price': 0},
    'trade2': {'ce_active': False, 'pe_active': False, 'ce_exited': False, 'pe_exited': False,
               'ce_scrip': None, 'pe_scrip': None, 'ce_strike': None, 'pe_strike': None, 'ce_sl': 0, 'pe_sl': 0,
               'ce_traded_price': 0, 'pe_traded_price': 0},
    'trade3': {'ce_active': False, 'pe_active': False, 'ce_exited': False, 'pe_exited': False,
               'ce_scrip': None, 'pe_scrip': None, 'ce_strike': None, 'pe_strike': None, 'ce_sl': 0, 'pe_sl': 0,
               'ce_traded_price': 0, 'pe_traded_price': 0}
}


# Initialize 5paisa client
#This function will automatically take care of generating and sending access token for all your API's
client = FivePaisaClient(cred=cr.cred)

# Generate TOTP
totp = pyotp.TOTP(cr.totp_key)
current_otp = totp.now()

# New TOTP based authentication
client.get_totp_session(cr.clientId, current_otp, cr.pin)

config = configparser.ConfigParser()
masignalpath = "masignal.ini"


def getatmStrike():
    config.read(masignalpath)
    ltp =config['sensex']['sensex']
    ltp = float(ltp)
    if ltp != 0:
        atmstrike=round(ltp/100)*100
    return atmstrike
    
def getspotprice():
    config.read(masignalpath)
    ltp =config['sensex']['sensex']
    ltp = float(ltp)
    return ltp

def get_scripcode(symbol, strike,expiry,opt):
   
        month={
            "01":'JAN',
            "02":'FEB',
            "03":'MAR',
            "04":'APR',
            "05":'MAY',
            "06":'JUN',
            "07":'JUL',
            "08":'AUG',
            "09":'SEP',
            "10":'OCT',
            "11":'NOV',
            "12":'DEC'      
        }
        date=expiry[6:]
        mon=month[expiry[4:6]]
        year=expiry[:4]
        symbol=symbol.upper()
        strike_f="{:.2f}".format(float(strike))
        sym=f'{symbol} {date} {mon} {year} {opt} {strike_f}'

        req=[{"Exch":"B","ExchType":"D","Symbol":sym,"Expiry":expiry,"StrikePrice":strike,"OptionType":opt}]
        res=client.fetch_market_feed(req)
        token=res['Data'][0]['Token']
        lastrate=res['Data'][0]['LastRate']
        return token , lastrate

def calculate_otm_strikes(atmstrike):

    """Generate strike levels """
    step_size = 100
    steps_up = 15
    steps_down =15
    strikes = []

    for i in range(steps_up + 1):
        up = atmstrike + (i * step_size)
        strikes.append(('CE', up))

    for i in range(1, steps_down + 1):
        dn = atmstrike - (i * step_size)
        strikes.append(('PE', dn))

    return list(dict.fromkeys(strikes))


def next_expiry():
    """Return next expiry YYYYMMDD, or Wednesday if expiry is a holiday."""
    
    # Define holidays (modify this list as needed)
    holidays = {
        '20251002',  # Gandhi Jayanti
        '20251225',  # Christmas
        '20251031',  # Diwali
        '20251226',  # Boxing Day
        # Add more holidays as needed
    }
    
    today = datetime.now()
    days = 3 - today.weekday()  # expiry is weekday 3
    if days <= 0:
        days += 7
    
    th = today + timedelta(days=days)
    
    # Check if expiry is a holiday
    if th.strftime('%Y%m%d') in holidays:
        # Return Wednesday instead (one day earlier)
        wed = th - timedelta(days=1)
        return wed.strftime('%Y%m%d')
    
    return th.strftime('%Y%m%d')

def scan_sensex():
    atmstrike = getatmStrike()
    expiry = next_expiry()
    print(expiry)
    strikes = calculate_otm_strikes(atmstrike)
    results = []
    for opt, strike in strikes:
        try:
            code, prem = get_scripcode(symbol, strike, expiry, opt)
        except Exception as e:
            print(f"[scan_sensex] Skipping {opt} {strike}: {e}")
            continue

        if prem is None:
            print(f"[scan_sensex] No premium for {opt} {strike}, skipping")
            continue
      
        if TARGET_PREMIUM - PREMIUM_TOLERANCE <= prem <= TARGET_PREMIUM + PREMIUM_TOLERANCE:
            results.append((strike,opt,prem, code))
    if not results:
        print("No options near ₹80 found.")
        return None, None, None, None
    else:
        
        # Find best PE from PE options only
        pe_options = [r for r in results if r[1] == 'PE']
        bestPE = min(pe_options, key=lambda x:abs(x[2]-TARGET_PREMIUM)) if pe_options else None

        # Find best CE from CE options only  
        ce_options = [r for r in results if r[1] == 'CE']
        bestCE = min(ce_options, key=lambda x:abs(x[2]-TARGET_PREMIUM)) if ce_options else None

        pestrike = bestPE[0]
        pescrip = bestPE[3]
        cestrike = bestCE[0]
        cescrip = bestCE[3]
        print("CE Trade - ", 'Strike: ', bestCE[0], "CE"  ', Premium: ', bestCE[2] )
        print("PE Trade - ", 'Strike: ', bestPE[0], "PE"  ', Premium: ', bestPE[2] )
        return pestrike, pescrip, cestrike, cescrip

def getTradedPrice(brokerid, orders, trades):
    try:
        exchOrderId = None
        for order in orders:
            if order["BrokerOrderId"] == brokerid:
                exchOrderId = order["ExchOrderID"]
                break
        if exchOrderId is None:
            raise Exception(f"ExchOrderId not found for BrokerOrderId: {brokerid}")
        tradebook = trades['TradeBookDetail']
        for trade in tradebook:
            if trade["ExchOrderID"] == exchOrderId:
                return trade["Rate"]
        raise Exception(f"Traded price not found for ExchOrderId: {exchOrderId}")
    except Exception as e:
        print(f"[Error in getTradedPrice]: {e}")
        return None

def getIntradayPnL():
    positionsInt = client.positions()
    PnL = 0
    for item in positionsInt:
        if (item['OrderFor'] == 'I') and ("SENSEX" in item['ScripName']):
            booked_pl = item['BookedPL']
            sell_qty = item['SellQty']
            buy_qty = item['BuyQty']
            sell_avg_rate = item['SellAvgRate']
            buy_avg_rate = item['BuyAvgRate']
            ltp = item['LTP']
            netqty = item["NetQty"]
            if netqty <= 0 :
                result = booked_pl + (sell_qty - buy_qty) * (sell_avg_rate - ltp)
            if netqty >= 0 :
                result = booked_pl + (buy_qty - sell_qty) * (ltp - buy_avg_rate)
            PnL = PnL + result
    return PnL

def get_current_price(symbol, strike, expiry, opt):
    try:
        code, prem = get_scripcode(symbol, strike, expiry, opt)
        return prem
    except:
        return None
    
def exit_position(scrip_code, qty, trade_name, option_type):
    global positions
    try:
        # Exit the position buy squaring off short position
        client.place_order(OrderType='B', Exchange='B', ExchangeType='D',
                           ScripCode=scrip_code, Qty=qty, Price=0, IsIntraday=True)
        print(f"Exited {trade_name} {option_type}")
        positions[trade_name][f"{option_type.lower()}_active"] = False
        positions[trade_name][f"{option_type.lower()}_exited"] = True
        return True
    except Exception as e:
        print(f"Exit Error {trade_name} {option_type}: {e}")
        return False

def reenter_position(symbol, strike, scrip_code, qty, trade_name, opt):
    """Re-enter using the same exited_scrip once price ≤ 80."""
    global positions

    price = get_current_price(symbol, strike, next_expiry(), opt)

    if price is None or price > tradePremium:
        return  # No re-entry if price is None or above 80
    
    # Re-enter the position 
    try:
        order = client.place_order(OrderType='S', Exchange='B', ExchangeType='D',
                           ScripCode=scrip_code, Qty=qty, Price=0, IsIntraday=True)
        orders = client.order_book()  
        trades = client.get_tradebook()
        tp = getTradedPrice(order['BrokerOrderID'], orders, trades)
        if tp is None:
            # handle error
            print(f"Re-entry failed: Traded price not found for {trade_name} {opt}")
            return
        else:
            tp = float(tp)
  
        positions[trade_name].update({
            f"{opt.lower()}_active": True,
            f"{opt.lower()}_exited": False,
            f"{opt.lower()}_scrip": scrip_code,
            f"{opt.lower()}_sl": tp * 1.2
        })
        print(f"RE-ENTRY: {trade_name} {opt} at ₹{tp}, SL ₹{tp*1.2}")
    except Exception as e:
        print(f"Re-entry Error {trade_name} {opt}: {e}")    

def monitor_and_manage_positions():
    global positions
    for trade_name, data in positions.items():
        sleep(.5)  # Small delay to avoid rapid API calls
        # CE SL
        if data['ce_active']:
            # symbol, strike,expiry,opt
            price = get_current_price(symbol, data['ce_strike'], next_expiry(), 'CE')
            if price is not None and price >= data['ce_sl']:
                exit_position(data['ce_scrip'], qty, trade_name, 'CE')
        # PE SL
        if data['pe_active']:
            price = get_current_price(symbol, data['pe_strike'], next_expiry(), 'PE')
            if price is not None and price >= data['pe_sl']:
                exit_position(data['pe_scrip'], qty, trade_name, 'PE')

        # Re-entry (CE)
        if data['ce_exited'] and not data['ce_active']:
            reenter_position(symbol, data['ce_strike'],data['ce_scrip'], qty, trade_name, 'CE')

        # Re-entry (PE)
        if data['pe_exited'] and not data['pe_active']:
            reenter_position(symbol, data['pe_strike'],data['pe_scrip'], qty, trade_name, 'PE')

if __name__=="__main__":
    statuschk = 0
    executed_trades = 0
    PnL = 0
    try:
        while True:
            statuschk += 1
            now = datetime.now(tz=gettz('Asia/Kolkata')) 
            
            try:
                    currentatmstrike = getatmStrike()
                    # currentspot = getspotprice()
                    if statuschk == 10:
                        PnL = getIntradayPnL()
                        print("program running. current atmstrike is: ", currentatmstrike ,  "time is: ", now.hour, " ", now.minute, "PnL is: ", PnL )
                        statuschk = 0
                        PnL = 0

            except: 
                continue
                       
            current_time = now.strftime("%H:%M")

        
            # Execute trades at exact times
            if current_time >= "09:45" and executed_trades == 0:
                entry_time = current_time
                scan_result = scan_sensex()
                
                if scan_result == (None, None, None, None):
                    print("No suitable options found, skipping this entry time")
                    continue  # Skip this iteration
                pestrike, pescrip, cestrike, cescrip = scan_result

                #Sell strangle
                ceorder = client.place_order(OrderType='S',Exchange='B',ExchangeType='D', ScripCode = cescrip, Qty=qty,  Price=0, IsIntraday = True)
                peorder = client.place_order(OrderType='S',Exchange='B',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)
                sleep(.5)
                orders = client.order_book()  
                sleep(.5)
                trades = client.get_tradebook()
                sleep(.5)

                ceTradedPrice = getTradedPrice(ceorder['BrokerOrderID'], orders, trades)
                if ceTradedPrice is None:
                    ceTradedPrice = 75 #Manually setting to 75 if error in getting traded price
                    print("Error: Could not get CE traded price, setting to 75")                    
                ceTradedPrice = float(ceTradedPrice)

                peTradedPrice = getTradedPrice(peorder['BrokerOrderID'], orders, trades)
                if peTradedPrice is None:
                    peTradedPrice = 75 #Manually setting to 75 if error in getting traded price
                    print("Error: Could not get PE traded price, setting to 75")
                peTradedPrice = float(peTradedPrice)

                executed_trades = 1
                # Update position tracking
                positions['trade1'].update({
                'ce_active': True, 'pe_active': True,
                'ce_scrip': cescrip, 'pe_scrip': pescrip,
                'ce_strike': cestrike, 'pe_strike': pestrike,
                'ce_sl': ceTradedPrice * 1.2, 'pe_sl': peTradedPrice * 1.2,
                'ce_traded_price': ceTradedPrice, 'pe_traded_price': peTradedPrice })

            elif current_time >= "10:45" and (executed_trades == 0 or executed_trades == 1):
                scan_result = scan_sensex()
                
                if scan_result == (None, None, None, None):
                    print("No suitable options found, skipping this entry time")
                    continue  # Skip this iteration
                pestrike, pescrip, cestrike, cescrip = scan_result
                #Sell strangle
                ceorder = client.place_order(OrderType='S',Exchange='B',ExchangeType='D', ScripCode = cescrip, Qty=qty,  Price=0, IsIntraday = True)
                peorder = client.place_order(OrderType='S',Exchange='B',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)
                sleep(.5)
                orders = client.order_book()  
                sleep(.5)
                trades = client.get_tradebook()
                sleep(.5)

                ceTradedPrice = getTradedPrice(ceorder['BrokerOrderID'], orders, trades)
                if ceTradedPrice is None:
                    ceTradedPrice = 75 #Manually setting to 75 if error in getting traded price
                    print("Error: Could not get CE traded price, setting to 75")                    
                ceTradedPrice = float(ceTradedPrice)

                peTradedPrice = getTradedPrice(peorder['BrokerOrderID'], orders, trades)
                if peTradedPrice is None:
                    peTradedPrice = 75 #Manually setting to 75 if error in getting traded price
                    print("Error: Could not get PE traded price, setting to 75")
                peTradedPrice = float(peTradedPrice)

                executed_trades = 2   
                # Update position tracking
                positions['trade2'].update({
                'ce_active': True, 'pe_active': True,
                'ce_scrip': cescrip, 'pe_scrip': pescrip,
                'ce_strike': cestrike, 'pe_strike': pestrike,
                'ce_sl': ceTradedPrice * 1.2, 'pe_sl': peTradedPrice * 1.2,
                'ce_traded_price': ceTradedPrice, 'pe_traded_price': peTradedPrice })

            elif current_time >= "11:45" and (executed_trades == 0 or executed_trades == 1 or executed_trades == 2):
                scan_result = scan_sensex()
                if scan_result == (None, None, None, None):
                    print("No suitable options found, skipping this entry time")
                    continue  # Skip this iteration
                pestrike, pescrip, cestrike, cescrip = scan_result
                #Sell strangle
                ceorder = client.place_order(OrderType='S',Exchange='B',ExchangeType='D', ScripCode = cescrip, Qty=qty,  Price=0, IsIntraday = True)
                peorder = client.place_order(OrderType='S',Exchange='B',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)
                sleep(.5)
                orders = client.order_book()  
                sleep(.5)
                trades = client.get_tradebook()
                sleep(.5)
                
                ceTradedPrice = getTradedPrice(ceorder['BrokerOrderID'], orders, trades)
                if ceTradedPrice is None:
                    ceTradedPrice = 75 #Manually setting to 75 if error in getting traded price
                    print("Error: Could not get CE traded price, setting to 75")                    
                ceTradedPrice = float(ceTradedPrice)

                peTradedPrice = getTradedPrice(peorder['BrokerOrderID'], orders, trades)
                if peTradedPrice is None:
                    peTradedPrice = 75 #Manually setting to 75 if error in getting traded price
                    print("Error: Could not get PE traded price, setting to 75")
                peTradedPrice = float(peTradedPrice)

                executed_trades = 3
                # Update position tracking
                positions['trade3'].update({
                'ce_active': True, 'pe_active': True,
                'ce_scrip': cescrip, 'pe_scrip': pescrip,
                'ce_strike': cestrike, 'pe_strike': pestrike,
                'ce_sl': ceTradedPrice * 1.2, 'pe_sl': peTradedPrice * 1.2,
                'ce_traded_price': ceTradedPrice, 'pe_traded_price': peTradedPrice })

            #monitor for SL hits and re-entries ..  
            if executed_trades > 0:     
                monitor_and_manage_positions()

            PnL = getIntradayPnL()
            lots = qty / 20
            PnLperLot = PnL/lots
            lossLimit = -4500
            PnL = 0

            # Exit all positions at 3:15 PM
            if (current_time >= "14:45" and executed_trades > 0) or (PnLperLot <= lossLimit):
                for trade_name, data in positions.items():
                    if data['ce_active']:
                        exit_position(data['ce_scrip'], qty, trade_name, 'CE')
                    if data['pe_active']:
                        exit_position(data['pe_scrip'], qty, trade_name, 'PE')   

                PnL = getIntradayPnL()  
                print("Exiting all positions before market close with PnL:", PnL)            
                GsheetLog.WriteTradeInGsheet(entry_time, currentatmstrike, 0, 0, 0, qty, PnL)         
                executed_trades = 0  # Reset for next day
                break


            sleep(30)

    except KeyboardInterrupt:
        #Exit all positions on keyboard interrupt
        sleep(1)
        print("Exiting all positions as keyboard close is initiated.")
        for trade_name, data in positions.items():
            if data['ce_active']:
                exit_position(data['ce_scrip'], qty, trade_name, 'CE')
            if data['pe_active']:
                exit_position(data['pe_scrip'], qty, trade_name, 'PE')
        executed_trades = 0  # Reset for next day
        PnL = getIntradayPnL()
        GsheetLog.WriteTradeInGsheet(entry_time, currentatmstrike, 0, 0, 0, qty, PnL)

        print("Program interrupted. Exited all positions with PnL:", PnL)
    except Exception as e:
        print(f"Error: {e}")
    finally:   
        pass


print('program ended')
