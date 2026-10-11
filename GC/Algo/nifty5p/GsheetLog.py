import pygsheets
import pandas as pd
from datetime import datetime as dtime
import datetime
from dateutil.tz import gettz
import sys

if not sys.warnoptions:
    import warnings
    warnings.simplefilter("ignore")
#authorization
gc = pygsheets.authorize(service_file='gsheetcred.json')
#open the google spreadsheet 
sh = gc.open('Intraday')
#select the first sheet 
wks = sh[0]
#retrieve all rows of the worksheet
cells = wks.get_all_values(include_tailing_empty_rows=False, include_tailing_empty=False, returnas='matrix')
#extract all non empty rows
nonEmptyRows = []
for i in cells:
    if i != []:
        nonEmptyRows.append(i)

#calculating the length 
countOfnonEmptyRows = len(nonEmptyRows)
type(countOfnonEmptyRows)
#inserting data 
def WriteTradeInGsheet(entry_time, atmPrice, totalPremiumCollected, totalPremiumGiven, profitPoints, qty, PnL):
    dateToday = datetime.date.today()
    dateToday = str(dateToday)
    dayToday = datetime.date.today().strftime("%A")   
    exitTime = dtime.now(tz=gettz('Asia/Kolkata')).strftime('%H:%M')
    profit = profitPoints*qty
    insertRow = [dateToday, dayToday, entry_time, exitTime, atmPrice, totalPremiumCollected, totalPremiumGiven, profitPoints, qty, profit, PnL]
    wks.insert_rows(countOfnonEmptyRows, values=insertRow, inherit=True) 
