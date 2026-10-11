import credentials as cr
#from py5paisa import FivePaisaClient
from py5paisa.strategy import *
from datetime import date, datetime
import time
from time import sleep
import requests
import configparser
from dateutil.tz import gettz
import GsheetLog  

now = datetime.now(tz=gettz('Asia/Kolkata')) 

exitHr = 14
exitMin = 45

symbol = "NIFTY"
qty = 25

expiry_date = date(2024, 11, 14)
expiry = "20241114"

config = configparser.ConfigParser()
masignalpath = "masignal.ini"


entry_time = datetime.now(tz=gettz('Asia/Kolkata')).strftime('%H:%M')

client = FivePaisaClient(email=cr.email, passwd=cr.password, dob=cr.dob, cred=cr.cred)
client.login()


def getatmStrike():
    config.read(masignalpath)
    ltp =config['indexltp']['indexspot']
    ltp = float(ltp)
    if ltp != 0:
        atmstrike=round(ltp/50)*50
    return atmstrike
    
def getspotprice():
    config.read(masignalpath)
    ltp =config['indexltp']['indexspot']
    ltp = float(ltp)
    return ltp

atmstrike = getatmStrike()

def get_scripcode(symbol,strike,expiry,opt):
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
        req=[{"Exch":"N","ExchType":"D","Symbol":sym,"Expiry":expiry,"StrikePrice":strike,"OptionType":opt}]

        res=client.fetch_market_feed(req)
        token=res['Data'][0]['Token']
        return token

cescrip = get_scripcode(symbol, atmstrike, expiry, "CE")
pescrip = get_scripcode(symbol, atmstrike, expiry, "PE")



#Sell Straddle
ceorder = client.place_order(OrderType='S',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty,  Price=0, IsIntraday = True)
peorder = client.place_order(OrderType='S',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)


def getTradedPrice(brokerid):      
    for order in orders:        
        if order["BrokerOrderId"] == brokerid:
            exchOrderId = order["ExchOrderID"]            
            break    
    tradebook = trades['TradeBookDetail']
    for trade in tradebook:        
        if trade["ExchOrderID"] == exchOrderId:
            tradedPrice = trade["Rate"]            
            break
    return tradedPrice

def getCombinedPrem():
    
    ceTradedPrice = float(getTradedPrice(ceorder['BrokerOrderID']))
    peTradedPrice = float(getTradedPrice(peorder['BrokerOrderID']))
    combined_premium = ceTradedPrice + peTradedPrice
    return combined_premium

sleep(2)
orders = client.order_book()  
trades = client.get_tradebook()
combined_premium = getCombinedPrem()
print(f"combined premium for strike: {atmstrike} is {combined_premium}")

#set STOPLOSS and Target
# stoplossValue = combined_premium + 20
# targetProfit = combined_premium - 20

# Monitor till exit criteria is met.
# Initiate square off orders once exit criteria conditions are satisfied
statuschk = 0
try:
    while True:
        statuschk = statuschk + 1

        try:
                currentatmstrike = getatmStrike()
                # currentspot = getspotprice()
                if statuschk == 11:
                    print("program running. current atmstrike is: ", currentatmstrike ,  "time is: ", now.hour, " ", now.minute)
                    statuschk = 1
                # if currentspot == 0:
                #     currentspot = currentatmstrike
                # signal = int(readmasignal())
        except: 
            continue
        
        now = datetime.now(tz=gettz('Asia/Kolkata')) 
        if (currentatmstrike == atmstrike + 100) or (currentatmstrike == atmstrike - 100) :
            
            #Buy Straddle
            ceorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty, Price=0, IsIntraday = True)
            peorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)

            sleep(2)
            orders = client.order_book()  
            trades = client.get_tradebook()
            combined_premium_sqr = getCombinedPrem()

            
            print('Total premium at exit:', combined_premium_sqr)
            profitPoints = combined_premium - combined_premium_sqr
            print('Points earned per lot: ', profitPoints)
            print('Total Profit: ', profitPoints*qty )
            GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, combined_premium, combined_premium_sqr, profitPoints, qty)
            
            atmstrike = currentatmstrike
            cescrip = get_scripcode(symbol, atmstrike, expiry, "CE")
            pescrip = get_scripcode(symbol, atmstrike, expiry, "PE")
            #Sell Straddle
            ceorder = client.place_order(OrderType='S',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty, Price=0, IsIntraday = True)
            peorder = client.place_order(OrderType='S',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)  
            sleep(2)
            orders = client.order_book()  
            trades = client.get_tradebook()
            combined_premium = getCombinedPrem()
            print(f"combined premium for strike: {atmstrike} is {combined_premium}")

        if (now.hour == exitHr  and now.minute >= exitMin):
            
            #buy Straddle
            ceorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty, Price=0, IsIntraday = True)
            peorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)
            sleep(2)
            orders = client.order_book()  
            trades = client.get_tradebook()
            combined_premium_sqr = getCombinedPrem()
            print('Total premium at exit:', combined_premium_sqr)
            profitPoints = combined_premium - combined_premium_sqr
            print('Points earned per lot: ', profitPoints)
            print('Total Profit: ', profitPoints*qty )
            GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, combined_premium, combined_premium_sqr, profitPoints, qty)
            break
        sleep(30) # Change as per your need

except KeyboardInterrupt:
    #buy Straddle
    sleep(1)
    print(cescrip)
    print(pescrip)
    ceorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty, Price=0, IsIntraday = True)
    sleep(1)
    peorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)
    sleep(1)
   
    orders = client.order_book()  
    trades = client.get_tradebook()
    combined_premium_sqr = getCombinedPrem()
    print('Total premium at exit:', combined_premium_sqr)
    profitPoints = combined_premium - combined_premium_sqr
    print('Points earned per lot: ', profitPoints)
    print('Total Profit: ', profitPoints*qty )
    GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, combined_premium, combined_premium_sqr, profitPoints, qty)
   

print('program ended')
