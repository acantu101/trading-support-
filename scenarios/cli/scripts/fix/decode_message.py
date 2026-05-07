#!/usr/bin/env python3
"""
FIX Message Decoder
====================
Decodes a raw FIX message (SOH or pipe-delimited) into readable tag=value pairs.

Usage:
    python3 decode_message.py "8=FIX.4.4|35=D|49=FIRM|55=AAPL|..."
    echo "8=FIX.4.4\x0135=D\x01..." | python3 decode_message.py
    cat message.fix | python3 decode_message.py
"""

import sys

SOH = "\x01"

TAGS = {
    "8":   "BeginString",    "9":   "BodyLength",     "35":  "MsgType",
    "49":  "SenderCompID",   "56":  "TargetCompID",   "34":  "MsgSeqNum",
    "52":  "SendingTime",    "43":  "PossDupFlag",    "10":  "CheckSum",
    "11":  "ClOrdID",        "37":  "OrderID",        "17":  "ExecID",
    "55":  "Symbol",         "54":  "Side",           "38":  "OrderQty",
    "40":  "OrdType",        "44":  "Price",          "59":  "TimeInForce",
    "60":  "TransactTime",   "41":  "OrigClOrdID",
    "39":  "OrdStatus",      "150": "ExecType",       "31":  "LastPx",
    "32":  "LastQty",        "14":  "CumQty",         "151": "LeavesQty",
    "6":   "AvgPx",          "58":  "Text",
    "98":  "EncryptMethod",  "108": "HeartBtInt",     "112": "TestReqID",
    "45":  "RefSeqNum",      "7":   "BeginSeqNo",     "16":  "EndSeqNo",
}

MSG_TYPES = {
    "0": "Heartbeat",       "1": "TestRequest",       "2": "ResendRequest",
    "3": "Reject",          "5": "Logout",            "8": "ExecutionReport",
    "A": "Logon",           "D": "NewOrderSingle",    "F": "OrderCancelRequest",
    "G": "OrderCancelReplaceRequest",
}

SIDES      = {"1": "BUY",  "2": "SELL", "5": "SELL SHORT"}
ORD_STATUS = {"0": "New",  "1": "PartialFill", "2": "Filled",
              "4": "Cancelled", "8": "Rejected"}
ORD_TYPES  = {"1": "Market", "2": "Limit", "3": "Stop", "4": "StopLimit"}
EXEC_TYPES = {"0": "New", "1": "PartialFill", "2": "Fill",
              "4": "Cancelled", "8": "Rejected"}
TIF        = {"0": "Day", "1": "GoodTillCancel", "3": "ImmOrCancel",
              "4": "FillOrKill"}


def decode(raw: str) -> dict:
    # Accept pipe-delimited or SOH-delimited
    raw = raw.replace("|", SOH).replace("\\x01", SOH)
    fields = {}
    for pair in raw.split(SOH):
        if "=" in pair:
            t, v = pair.split("=", 1)
            fields[t.strip()] = v.strip()
    return fields


def enrich(tag: str, val: str) -> str:
    if tag == "35":  return f"{val} ({MSG_TYPES.get(val, 'Unknown')})"
    if tag == "54":  return f"{val} ({SIDES.get(val, val)})"
    if tag == "39":  return f"{val} ({ORD_STATUS.get(val, val)})"
    if tag == "150": return f"{val} ({EXEC_TYPES.get(val, val)})"
    if tag == "40":  return f"{val} ({ORD_TYPES.get(val, val)})"
    if tag == "59":  return f"{val} ({TIF.get(val, val)})"
    if tag == "43":  return f"{val} ({'RESENT' if val == 'Y' else 'original'})"
    return val


def display(raw: str):
    fields   = decode(raw)
    msg_type = fields.get("35", "?")

    print("=" * 55)
    print(f"MsgType : {MSG_TYPES.get(msg_type, 'Unknown')} (35={msg_type})")
    print(f"Seq     : {fields.get('34', '?')}")
    print(f"From    : {fields.get('49', '?')}  →  {fields.get('56', '?')}")
    print(f"Time    : {fields.get('52', '?')}")

    if msg_type == "D":
        print(f"Order   : {SIDES.get(fields.get('54'), '?')} "
              f"{fields.get('38', '?')} {fields.get('55', '?')} "
              f"@ ${fields.get('44', 'MARKET')} "
              f"[{ORD_TYPES.get(fields.get('40', ''), '?')}]")
    elif msg_type == "8":
        status = ORD_STATUS.get(fields.get("39", ""), fields.get("39", "?"))
        print(f"Status  : {status} (39={fields.get('39', '?')})")
        print(f"LastPx  : {fields.get('31', '?')}  "
              f"LastQty: {fields.get('32', '?')}  "
              f"CumQty: {fields.get('14', '?')}  "
              f"LeavesQty: {fields.get('151', '?')}")
        if fields.get("58"):
            print(f"Reason  : {fields['58']}")
    elif msg_type == "3":
        print(f"REJECT  : RefSeq={fields.get('45', '?')}  "
              f"Reason={fields.get('58', '?')}")
    elif msg_type == "2":
        print(f"RESEND  : BeginSeqNo={fields.get('7', '?')}  "
              f"EndSeqNo={fields.get('16', '?')}")
    elif msg_type == "A":
        print(f"Logon   : HeartBtInt={fields.get('108', '?')}s  "
              f"EncryptMethod={fields.get('98', '?')}")

    print("\nAll fields:")
    for tag, val in fields.items():
        name    = TAGS.get(tag, f"Tag{tag}")
        display_val = enrich(tag, val)
        print(f"  {tag:>4} = {display_val:<35}  ({name})")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        display(" ".join(sys.argv[1:]))
    elif not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line and ("35=" in line or "8=FIX" in line):
                display(line)
    else:
        print("Usage:")
        print('  python3 decode_message.py "8=FIX.4.4|35=D|55=AAPL|..."')
        print("  cat message.fix | python3 decode_message.py")
