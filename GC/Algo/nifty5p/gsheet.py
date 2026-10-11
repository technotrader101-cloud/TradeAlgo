import pygsheets
import pandas as pd
#authorization
gc = pygsheets.authorize(service_file='gsheetcred.json')

# Create empty dataframe
df = pd.DataFrame()

# Create a column
df['name'] = ['John', 'Steve', 'Sarah']

#open the google spreadsheet (where 'PY to Gsheet Test' is the name of my sheet)
sh = gc.open('GsheetTest')

#select the first sheet 
wks = sh[0]

#update the first sheet with df, starting at cell B2. 
wks.set_dataframe(df,(1,1))

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

#defining the data
ls = ['G', 'H', 'I']


#inserting data 
wks.insert_rows(countOfnonEmptyRows, values=ls, inherit=True) 