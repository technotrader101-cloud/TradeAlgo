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

exitHr = 15
exitMin = 12

symbol = "NIFTY"
qty = 75

expiry = "20250626"

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

def getIntradayPnL():
    positions = client.positions()
    PnL = 0
    for item in positions:
        if (item['OrderFor'] == 'I'):
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

def closeIntradayPositions():
    positions = client.positions()
    for item in positions:
        if (item['OrderFor'] == 'I'):
            netqty = item["NetQty"]
            scripcode = item["ScripCode"]
            if netqty > 0 :
                client.place_order(OrderType='S',Exchange='N',ExchangeType='D', ScripCode = scripcode, Qty=netqty,  Price=0, IsIntraday = True)
            if netqty < 0 :
                netqty =abs(netqty)
                client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = scripcode, Qty=netqty,  Price=0, IsIntraday = True)
           
cescrip = get_scripcode(symbol, atmstrike + 200, expiry, "CE")
pescrip = get_scripcode(symbol, atmstrike - 200, expiry, "PE")

#Sell strangle
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
ceTradedPrice = float(getTradedPrice(ceorder['BrokerOrderID']))
peTradedPrice = float(getTradedPrice(peorder['BrokerOrderID']))
combined_premium = getCombinedPrem()
print(f"combined premium for strike: {atmstrike} is {combined_premium}")

#set STOPLOSS and Target
# stoplossValue = combined_premium + 20
# targetProfit = combined_premium - 20

# Monitor till exit criteria is met.
# Initiate square off orders once exit criteria conditions are satisfied
statuschk = 0
PnL = 0
try:
    while True:
        statuschk = statuschk + 1

        try:
                currentatmstrike = getatmStrike()
                # currentspot = getspotprice()
                if statuschk == 11:
                    PnL = getIntradayPnL()
                    print("program running. current atmstrike is: ", currentatmstrike ,  "time is: ", now.hour, " ", now.minute, "PnL is: ", PnL )
                    statuschk = 1
                    PnL = 0

        except: 
            continue
        
        now = datetime.now(tz=gettz('Asia/Kolkata')) 
        if (currentatmstrike >= atmstrike + 100) or (currentatmstrike <= atmstrike - 100) :
            
            if(currentatmstrike >= atmstrike + 100):
                pescrip1 = get_scripcode(symbol, currentatmstrike - 100, expiry, "PE")
                if(pescrip1 != pescrip) :
                    #buy pe
                    peorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)
                    sleep(2)
                    orders = client.order_book()  
                    trades = client.get_tradebook()
                    peSqredPrice = float(getTradedPrice(peorder['BrokerOrderID']))
                    profitPoints = peTradedPrice - peSqredPrice
                    print('Points earned per lot: ', profitPoints)
                    print('Total Profit: ', profitPoints*qty )
                    GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, peTradedPrice, peSqredPrice, profitPoints, qty, PnL)
                    atmstrike = currentatmstrike
                    pescrip = pescrip1
                    #Sell pe
                    peorder = client.place_order(OrderType='S',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)  
                    sleep(2)
                    orders = client.order_book()  
                    trades = client.get_tradebook()
                    peTradedPrice = float(getTradedPrice(peorder['BrokerOrderID']))
                    print(f"pe sold: {atmstrike} is {peTradedPrice}")

            if(currentatmstrike <= atmstrike - 100):
                cescrip1 = get_scripcode(symbol, currentatmstrike + 100, expiry, "CE")
                if(cescrip1 != cescrip):
                    #buy pe
                    ceorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty, Price=0, IsIntraday = True)
                    sleep(2)
                    orders = client.order_book()  
                    trades = client.get_tradebook()                
                    ceSqredPrice = float(getTradedPrice(ceorder['BrokerOrderID']))
                    profitPoints = ceTradedPrice - ceSqredPrice
                    print('Points earned per lot: ', profitPoints)
                    print('Total Profit: ', profitPoints*qty )
                    GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, ceTradedPrice, ceSqredPrice, profitPoints, qty, PnL)
                    atmstrike = currentatmstrike
                    cescrip = cescrip1
                    #Sell ce
                    ceorder = client.place_order(OrderType='S',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty, Price=0, IsIntraday = True)  
                    sleep(2)
                    orders = client.order_book()  
                    trades = client.get_tradebook()
                    ceTradedPrice = float(getTradedPrice(ceorder['BrokerOrderID']))
                    print(f"ce sold: {atmstrike} is {ceTradedPrice}")

        PnL = getIntradayPnL()
        lots = qty / 75
        PnLperLot = PnL/lots
        lossLimit = -3000
        PnL = 0
        if (now.hour == exitHr  and now.minute >= exitMin) or (lossLimit > PnLperLot ):
            
            #buy ce pe
            ceorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty, Price=0, IsIntraday = True)
            peorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)
            
            sleep(2)
            orders = client.order_book()  
            trades = client.get_tradebook()

            peSqredPrice = float(getTradedPrice(peorder['BrokerOrderID']))
            profitPoints = peTradedPrice - peSqredPrice
            print('Points earned per lot: ', profitPoints)
            print('Total Profit: ', profitPoints*qty )
            GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, peTradedPrice, peSqredPrice, profitPoints, qty, PnL)

            ceSqredPrice = float(getTradedPrice(ceorder['BrokerOrderID']))
            profitPoints = ceTradedPrice - ceSqredPrice
            print('Points earned per lot: ', profitPoints)
            print('Total Profit: ', profitPoints*qty )
            PnL = getIntradayPnL()
            GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, ceTradedPrice, ceSqredPrice, profitPoints, qty, PnL)

            closeIntradayPositions()

            break
        sleep(30) # Change as per your need

except KeyboardInterrupt:
    #buy Straddle
    sleep(1)
    PnL = 0
    #buy ce pe
    ceorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = cescrip, Qty=qty, Price=0, IsIntraday = True)
    peorder = client.place_order(OrderType='B',Exchange='N',ExchangeType='D', ScripCode = pescrip, Qty=qty, Price=0, IsIntraday = True)
    sleep(2)
    orders = client.order_book()  
    trades = client.get_tradebook()

    peSqredPrice = float(getTradedPrice(peorder['BrokerOrderID']))
    profitPoints = peTradedPrice - peSqredPrice
    print('Points earned per lot: ', profitPoints)
    print('Total Profit: ', profitPoints*qty )
    GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, peTradedPrice, peSqredPrice, profitPoints, qty, PnL)

    ceSqredPrice = float(getTradedPrice(ceorder['BrokerOrderID']))
    profitPoints = ceTradedPrice - ceSqredPrice
    print('Points earned per lot: ', profitPoints)
    print('Total Profit: ', profitPoints*qty )
    PnL = getIntradayPnL()
    GsheetLog.WriteTradeInGsheet(entry_time, atmstrike, ceTradedPrice, ceSqredPrice, profitPoints, qty, PnL)

    closeIntradayPositions()

print('program ended')
