import sys

# ========= Filter 5paisa "Success" noise =========
class FilteredWriter:
    def __init__(self, orig):
        self.orig = orig
    def write(self, data):
        if "Success" in data:
            return
        self.orig.write(data)
    def flush(self):
        self.orig.flush()

sys.stdout = FilteredWriter(sys.stdout)

# ========= Imports & 5Paisa Auth  =========
import credentials as cr
from py5paisa import FivePaisaClient
from datetime import datetime, timedelta
import configparser
from dateutil.tz import gettz
from time import sleep
import pyotp
import GsheetLog


# ---------- 5Paisa client init ----------
client = FivePaisaClient(cred=cr.cred)

totp = pyotp.TOTP(cr.totp_key)
current_otp = totp.now()
client.get_totp_session(cr.clientId, current_otp, cr.pin)

# ========= Config =========
CONFIG_FILE = "masignal.ini"
config = configparser.ConfigParser()

symbol = "BANKNIFTY"    # BankNifty underlying

# ========= Single-position state =========
position = {
    "is_open": False,
    "side": None,
    "entry_spot": 0.0,
    "entry_price": 0.0,
    "scrip_code": None,
    "qty": 0,
    "entry_time": None,
    "exit_time": None,
    "exit_spot": 0.0,
}

# ========= Helpers to read masignal.ini =========
def load_bnf_config():
    """
    Reads spot from [bnfltp] and trade parameters from [BNF].
    Another program must keep [bnfltp].bnfltp updated.
    You manually edit [BNF] for levels and SL.
    """
    config.read(CONFIG_FILE)

    # Spot from [bnfltp]
    spot_sec = config["bnfltp"]
    bnfspot = float(spot_sec.get("bnfltp"))

    # Levels and controls from [BNF]
    bnf_sec = config["BNF"]
    bnflong = float(bnf_sec.get("bnflong").strip())
    bnfshort = float(bnf_sec.get("bnfshort").strip())
    option_sl = float(bnf_sec.get("optionSL", fallback="0"))
    qty = int(bnf_sec.get("qty", fallback="30"))
    reversal_points = float(bnf_sec.get("reversal_points", fallback="25"))

    return {
        "bnfspot": bnfspot,
        "bnflong": bnflong,
        "bnfshort": bnfshort,
        "option_sl": option_sl,
        "qty": qty,
        "reversal_points": reversal_points,
    }

# ========= Expiry calculation (BankNifty monthly) =========

def next_expiry():
    """
    BANKNIFTY monthly expiry:
    - Last Tuesday of the current month.
    - If that Tuesday is a trading holiday, exchange moves it to previous trading day,
      but here we just compute last Tuesday; you can add a holiday list if needed.
    Returns: YYYYMMDD string.
    """
    today = datetime.now()
    # Go to first day of next month
    if today.month == 12:
        first_next_month = datetime(today.year + 1, 1, 1)
    else:
        first_next_month = datetime(today.year, today.month + 1, 1)

    # Step back one day to get last day of current month
    last_day_this_month = first_next_month - timedelta(days=1)

    # Walk backwards to find last Tuesday (weekday=1; Mon=0)
    d = last_day_this_month
    while d.weekday() != 1:  # 1 = Tuesday
        d -= timedelta(days=1)

    # d is the last Tuesday of this month
    return d.strftime("%Y%m%d")


# ========= Option symbol / scrip lookup (5Paisa style) =========
def get_bnf_atm_strike(bnfspot):
    """
    Round BankNifty spot to nearest 100 for ATM strike.
    """
    return round(bnfspot / 100) * 100

def get_scripcode(symbol, strike, expiry, opt):
    """
    Same pattern as your Sensex get_scripcode(), but for BankNifty.
    Symbol format assumed as: BANKNIFTY DD MON YYYY CE/PE STRIKE.xx
    """
    month = {
        "01": 'JAN', "02": 'FEB', "03": 'MAR', "04": 'APR',
        "05": 'MAY', "06": 'JUN', "07": 'JUL', "08": 'AUG',
        "09": 'SEP', "10": 'OCT', "11": 'NOV', "12": 'DEC'
    }
    date = expiry[6:]
    mon = month[expiry[4:6]]
    year = expiry[:4]
    symbol = symbol.upper()
    strike_f = "{:.2f}".format(float(strike))
    sym = f"{symbol} {date} {mon} {year} {opt} {strike_f}"

    req = [{
        "Exch": "N",          # or "B" depending on how BankNifty is configured on your 5Paisa account
        "ExchType": "D",
        "Symbol": sym,
        "Expiry": expiry,
        "StrikePrice": strike,
        "OptionType": opt
    }]
    res = client.fetch_market_feed(req)
    token = res["Data"][0]["Token"]
    lastrate = res["Data"][0]["LastRate"]
    return token, lastrate

def get_option_ltp(symbol, strike, opt):
    expiry = next_expiry()
    _, prem = get_scripcode(symbol, strike, expiry, opt)
    return prem

# ========= Order helpers =========
def getTradedPrice(brokerid, orders, trades):
    exchOrderId = None
    for order in orders:
        if order["BrokerOrderId"] == brokerid:
            exchOrderId = order["ExchOrderID"]
            break
    if exchOrderId is None:
        raise Exception(f"ExchOrderId not found for BrokerOrderId: {brokerid}")
    tradebook = trades["TradeBookDetail"]
    for trade in tradebook:
        if trade["ExchOrderID"] == exchOrderId:
            return trade["Rate"]
    raise Exception(f"Traded price not found for ExchOrderId: {exchOrderId}")

def place_short_option_atm(bnfspot, side, qty):
    """
    side = "SHORT_CE" or "SHORT_PE"
    SHORT_CE: sell ATM CE
    SHORT_PE: sell ATM PE

    Returns True if order placed and position updated, else False.
    """
    global position
    try:
        atm = get_bnf_atm_strike(bnfspot)
        expiry = next_expiry()
        opt = "CE" if side == "SHORT_CE" else "PE"

        # Get scrip + LTP
        scrip_code, ltp = get_scripcode(symbol, atm, expiry, opt)

        # Place SELL MIS order
        order = client.place_order(
            OrderType="S",
            Exchange="N",          # adjust if needed for your 5paisa setup
            ExchangeType="D",
            ScripCode=scrip_code,
            Qty=qty,
            Price=0,              # market
            IsIntraday=True
        )

        sleep(0.5)
        orders = client.order_book()
        trades = client.get_tradebook()

        try:
            traded_price = float(getTradedPrice(order["BrokerOrderID"], orders, trades))
        except Exception as e:
            print(f"[WARN] Could not fetch traded price, using LTP. Error: {e}")
            traded_price = float(ltp)

        position.update({
            "is_open": True,
            "side": side,
            "entry_spot": bnfspot,
            "entry_price": traded_price,
            "scrip_code": scrip_code,
            "qty": qty,
            "entry_time": datetime.now(tz=gettz("Asia/Kolkata"))
        })

        print(f"ENTERED {side} | ATM {atm} {opt} @ {traded_price}, spot {bnfspot}")
        return True

    except Exception as e:
        # Order not placed; position must remain flat
        print(f"[ERROR] Failed to place short {side} order: {e}")
        return False

def square_off_position():
    """
    Squares off current position, logs to Gsheet, and clears state.
    """
    global position
    if not position["is_open"]:
        return

    try:
        # BUY to cover short
        client.place_order(
            OrderType="B",
            Exchange="N",
            ExchangeType="D",
            ScripCode=position["scrip_code"],
            Qty=position["qty"],
            Price=0,
            IsIntraday=True
        )
        print(f"Square off done for {position['side']}")
    except Exception as e:
        print(f"Error while squaring off: {e}")
        return

    # Capture exit info
    exit_time = datetime.now(tz=gettz("Asia/Kolkata"))
    exit_time_str = exit_time.astimezone(gettz("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    cfg = load_bnf_config()
    exit_spot = cfg["bnfspot"]

    # Get intraday PnL for logging
    pnl = getIntradayPnL()

    # Prepare values for sheet
    entry_time = position.get("entry_time")
    entry_time_str = (entry_time.astimezone(gettz("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    if entry_time is not None
    else "")

    entry_spot = position.get("entry_spot")
    qty = position.get("qty")

    try:
        GsheetLog.WriteTradeInGsheet(
            entry_time_str,      # entry_time (datetime or string)
            entry_spot,      # entry_spot
            position.get("entry_price", 0),  # entry option price
            exit_time_str,       # exit_time
            exit_spot,       # exit_spot
            qty,             # qty
            pnl              # total intraday PnL
        )
        print("Trade logged to Google Sheet.")
    except Exception as e:
        print(f"Error logging to Gsheet: {e}")

    # Reset
    position.update({
        "is_open": False,
        "side": None,
        "entry_spot": 0.0,
        "entry_price": 0.0,
        "scrip_code": None,
        "qty": 0,
        "entry_time": None,
        "exit_time": None,
        "exit_spot": 0.0,
    })

# ========= Entry and Exit logic =========
def check_for_entry(cfg):
    """
    Entry logic:
    - If no open position:
      - if bnfspot >= bnflong => SHORT_PE (sell ATM PE)
      - if bnfspot <= bnfshort => SHORT_CE (sell ATM CE)
    """
    global position
    if position["is_open"]:
        return

    spot = cfg["bnfspot"]
    bnflong = cfg["bnflong"]
    bnfshort = cfg["bnfshort"]
    qty = cfg["qty"]

    # Long bias breakout => sell ATM PE
    if spot >= bnflong:
        place_short_option_atm(spot, side="SHORT_PE", qty=qty)

    # Short bias breakdown => sell ATM CE
    elif spot <= bnfshort:
        place_short_option_atm(spot, side="SHORT_CE", qty=qty)

def check_for_exit(cfg):
    """
    Exit logic:
    1) Reversal: spot moves reversal_points in opposite direction from entry_spot.
    2) Option SL: if optionSL > 0 and (current_option_price >= entry_price + optionSL)
    """
    global position
    if not position["is_open"]:
        return

    spot = cfg["bnfspot"]
    option_sl = cfg["option_sl"]
    reversal_points = cfg["reversal_points"]

    # --- 1) Reversal-based exit on spot ---
    if position["side"] == "SHORT_PE":
        # LONG bias trade, adverse move is down
        if spot <= position["entry_spot"] - reversal_points:
            print(
                f"Reversal exit SHORT_PE: spot {spot} <= entry {position['entry_spot']} - {reversal_points}"
            )
            square_off_position()
            return

    elif position["side"] == "SHORT_CE":
        # SHORT bias trade, adverse move is up
        if spot >= position["entry_spot"] + reversal_points:
            print(
                f"Reversal exit SHORT_CE: spot {spot} >= entry {position['entry_spot']} + {reversal_points}"
            )
            square_off_position()
            return

    # --- 2) Option SL exit (if optionSL > 0) ---
    if option_sl > 0:
        # Determine current option LTP for the same strike
        atm = get_bnf_atm_strike(position["entry_spot"])
        opt = "CE" if position["side"] == "SHORT_CE" else "PE"
        try:
            ltp = float(get_option_ltp(symbol, atm, opt))
        except Exception as e:
            print(f"Error getting option LTP for SL: {e}")
            return

        if ltp >= position["entry_price"] + option_sl:
            print(
                f"Option SL exit: LTP {ltp} >= entry {position['entry_price']} + {option_sl}"
            )
            square_off_position()
            return

def getIntradayPnL():
    positions_int = client.positions()
    pnl = 0
    for item in positions_int:
        # Filter only BankNifty derivative intraday positions
        if item.get("OrderFor") == "I" and "BANKNIFTY" in item.get("ScripName", ""):
            booked_pl = item["BookedPL"]
            sell_qty = item["SellQty"]
            buy_qty = item["BuyQty"]
            sell_avg_rate = item["SellAvgRate"]
            buy_avg_rate = item["BuyAvgRate"]
            ltp = item["LTP"]
            netqty = item["NetQty"]

            if netqty <= 0:
                result = booked_pl + (sell_qty - buy_qty) * (sell_avg_rate - ltp)
            else:
                result = booked_pl + (buy_qty - sell_qty) * (ltp - buy_avg_rate)
            pnl += result
    return pnl

# ========= Main loop =========
def main_loop(poll_interval=1.0):
    statuschk = 0
    print("BankNifty breakout bot started, watching masignal.ini for levels...")

    while True:
        now = datetime.now(tz=gettz("Asia/Kolkata"))
        current_time = now.strftime("%H:%M")
        try:
            cfg = load_bnf_config()
        except Exception as e:
            print(f"Error loading BNF config: {e}")
            sleep(poll_interval)
            continue

        statuschk += 1
        if statuschk >= 120:
            print(
                f"{now} | spot={cfg['bnfspot']} long={cfg['bnflong']} short={cfg['bnfshort']} "
                f"optSL={cfg['option_sl']} rev={cfg['reversal_points']} is_open={position['is_open']} side={position['side']}"
            )
            statuschk = 0

        # Entry / Exit logic
        if not position["is_open"]:
            check_for_entry(cfg)
        else:
            check_for_exit(cfg)

        # Optional: time-based shutdown if desired (e.g., after 15:20)
        if current_time >= "15:15" and position["is_open"]:
            print("Time-based EOD exit.")
            square_off_position()
            break

        sleep(poll_interval)

if __name__ == "__main__":
    try:
        main_loop(poll_interval=5.0)
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, exiting...")
        if position["is_open"]:
            square_off_position()
        print("Program ended.")
