# enhanced_banknifty_strategy.py

import credentials as cr
from py5paisa.strategy import *
from datetime import date, datetime
import time
from time import sleep
import configparser
from dateutil.tz import gettz
import GsheetLog

# Configuration
exitHr, exitMin = 15, 14
symbol, qty, expiry = "BANKNIFTY", 70, "20250930"
masignalpath = "masignal.ini"
entry_time = datetime.now(tz=gettz('Asia/Kolkata')).strftime('%H:%M')

# Initialize client
client = FivePaisaClient(email=cr.email, passwd=cr.password, dob=cr.dob, cred=cr.cred)
client.login()

# Helper functions
def getatmStrike():
    config = configparser.ConfigParser()
    config.read(masignalpath)
    ltp = float(config['bnfltp']['bnfltp'])
    return round(ltp/100)*100 if ltp else 0

def getspotprice():
    config = configparser.ConfigParser()
    config.read(masignalpath)
    return float(config['bnfltp']['bnfltp'])

def get_scripcode(symbol, strike, expiry, opt):
    month = {
        "01":'JAN',"02":'FEB',"03":'MAR',"04":'APR',
        "05":'MAY',"06":'JUN',"07":'JUL',"08":'AUG',
        "09":'SEP',"10":'OCT',"11":'NOV',"12":'DEC'
    }
    d, m, y = expiry[6:], month[expiry[4:6]], expiry[:4]
    sym = f"{symbol} {d} {m} {y} {opt} {strike:.2f}"
    req = [{"Exch":"N","ExchType":"D","Symbol":sym,"Expiry":expiry,
            "StrikePrice":strike,"OptionType":opt}]
    return client.fetch_market_feed(req)['Data'][0]['Token']

def analyze_constituent_momentum():
    bullish, bearish = 0, 0
    for stock in ['HDFCBANK','ICICIBANK','SBIN','KOTAKBANK','AXISBANK','INDUSINDBK']:
        data = client.fetch_market_feed([{"Exch":"N","ExchType":"C","Symbol":stock}])['Data'][0]
        change = data.get('PercentChange',0)
        if change > 1.0: bullish += 1
        if change < -1.0: bearish += 1
    if bullish >= 3: return 'BULLISH'
    if bearish >= 3: return 'BEARISH'
    return 'NEUTRAL'

def get_vix_data():
    d = client.fetch_market_feed([{"Exch":"N","ExchType":"D","Symbol":"INDIAVIX"}])['Data'][0]
    return d['LastTradedPrice'], d['PrevClosePrice']

def check_vix_spike():
    curr, prev = get_vix_data()
    delta = curr - prev
    return ('SPIKE', delta) if abs(delta) > 2.0 else ('NORMAL', delta)

def get_option_oi(scrip):
    return client.fetch_market_feed([{"Exch":"N","ExchType":"D","ScripCode":scrip}])['Data'][0]['OpenInterest']

def analyze_option_oi(cc, pp):
    c, p = get_option_oi(cc), get_option_oi(pp)
    pcr = p/c if c else 1
    if pcr > 1.3: return 'BULLISH_OI'
    if pcr < 0.7: return 'BEARISH_OI'
    return 'NEUTRAL_OI'

def convert_to_directional(direction, call_strike, put_strike):
    hedge_qty = qty // 2
    if direction == 'BULLISH':
        hs = get_scripcode(symbol, put_strike-200, expiry, "PE")
        client.place_order('B','N','D',hs,hedge_qty,0,True)
    else:
        hs = get_scripcode(symbol, call_strike+200, expiry, "CE")
        client.place_order('B','N','D',hs,hedge_qty,0,True)
    print(f"Converted to {direction}, hedged at {hs}")

def getIntradayPnL():
    PnL = 0
    for item in client.positions():
        if item['OrderFor']=='I' and "BANKNIFTY" in item['ScripName']:
            net = item['NetQty']
            bp = item['BookedPL']
            ltp = item['LTP']
            if net <= 0:
                PnL += bp + (item['SellQty']-item['BuyQty'])*(item['SellAvgRate']-ltp)
            else:
                PnL += bp + (item['BuyQty']-item['SellQty'])*(ltp-item['BuyAvgRate'])
    return PnL

def closeIntradayPositions():
    for item in client.positions():
        if item['OrderFor']=='I' and "BANKNIFTY" in item['ScripName']:
            net, code = item['NetQty'], item['ScripCode']
            if net > 0:
                client.place_order('S','N','D',code,net,0,True)
            elif net < 0:
                client.place_order('B','N','D',code,abs(net),0,True)

def getTradedPrice(bid, orders, trades):
    for o in orders:
        if o["BrokerOrderId"]==bid:
            eid=o["ExchOrderID"]; break
    for t in trades['TradeBookDetail']:
        if t["ExchOrderID"]==eid:
            return t["Rate"]

# Main execution
atmstrike = getatmStrike()
cestrike, pestrike = atmstrike+500, atmstrike-500
cescrip = get_scripcode(symbol,cestrike,expiry,"CE")
pescrip = get_scripcode(symbol,pestrike,expiry,"PE")

# Sell OTM strangle
ceorder = client.place_order('S','N','D',cescrip,qty,0,True)
peorder = client.place_order('S','N','D',pescrip,qty,0,True)
sleep(2)
orders, trades = client.order_book(), client.get_tradebook()
entry_ce = getTradedPrice(ceorder['BrokerOrderID'], orders, trades)
entry_pe = getTradedPrice(peorder['BrokerOrderID'], orders, trades)
entry_prem = entry_ce + entry_pe
print(f"Entry ATM={atmstrike}, Premium={entry_prem}")

# Directional state
is_directional = False
directional_bias = None

# Monitoring loop
try:
    while True:
        now = datetime.now(tz=gettz('Asia/Kolkata'))
        if now.minute % 1 == 0:
            pnl = getIntradayPnL()
            print(f"{now.hour}:{now.minute} ATM={getatmStrike()} PnL={pnl}")

        curr_atm = getatmStrike()
        # Roll logic omitted for brevity...

        # Directional conversion
        if not is_directional:
            mom = analyze_constituent_momentum()
            vix_status, vix_delta = check_vix_spike()
            vix_dir = 'BEARISH' if vix_delta>0 else 'BULLISH'
            oi_sig = analyze_option_oi(cescrip,pescrip)
            oi_dir = 'BULLISH' if oi_sig=='BULLISH_OI' else 'BEARISH' if oi_sig=='BEARISH_OI' else None

            triggers = []
            if mom!='NEUTRAL': triggers.append(mom)
            if vix_status=='SPIKE': triggers.append(vix_dir)
            if oi_dir: triggers.append(oi_dir)

            if triggers.count('BULLISH')>=2:
                convert_to_directional('BULLISH', cestrike, pestrike)
                is_directional, directional_bias = True, 'BULLISH'
            elif triggers.count('BEARISH')>=2:
                convert_to_directional('BEARISH', cestrike, pestrike)
                is_directional, directional_bias = True, 'BEARISH'

        # Exit conditions...
        if (now.hour==exitHr and now.minute>=exitMin) or (getIntradayPnL() <= -3000):
            print("Exiting all positions")
            closeIntradayPositions()
            break

        sleep(30)

except KeyboardInterrupt:
    print("Manual exit")
    closeIntradayPositions()
