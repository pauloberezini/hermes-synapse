import sys
import os
import time
from datetime import datetime
from twisted.internet import reactor, ssl, protocol

SOH = "\x01"

class DiagnosticFIX(protocol.Protocol):
    def __init__(self, sender, target, password, subid, attempt_name):
        self.sender = sender
        self.target = target
        self.password = password
        self.subid = subid
        self.attempt_name = attempt_name
        self.msg_seq_num = 1

    def make_msg(self, msg_type, body_dict):
        header = {
            "8": "FIX.4.4",
            "35": msg_type,
            "49": self.sender,
            "56": self.target,
            "34": str(self.msg_seq_num),
            "52": datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3],
            "57": self.subid
        }
        full_dict = {**header, **body_dict}
        body_str = ""
        tags = ["35", "49", "56", "34", "52", "57"] + [t for t in body_dict.keys() if t not in header]
        for tag in tags:
            body_str += f"{tag}={full_dict[tag]}{SOH}"
        msg_header = f"8=FIX.4.4{SOH}9={len(body_str)}{SOH}"
        full_msg = msg_header + body_str
        checksum = sum(ord(c) for c in full_msg) % 256
        full_msg += f"10={checksum:03d}{SOH}"
        self.msg_seq_num += 1
        return full_msg.encode('ascii')

    def connectionMade(self):
        print(f"\n--- Attempt: {self.attempt_name} ---")
        print(f"Target: {self.target}, Sender: {self.sender}, SubID: {self.subid}")
        logon_body = {
            "98": "0",
            "108": "30",
            "141": "Y",
            "553": self.sender.split('.')[-1] if '.' in self.sender else self.sender,
            "554": self.password
        }
        self.transport.write(self.make_msg("A", logon_body))

    def dataReceived(self, data):
        raw = data.decode('ascii', errors='ignore')
        print(f"RECV: {raw.replace(SOH, '|')}")
        if "35=A" in raw:
            print(f"✅ SUCCESS on {self.attempt_name}!")
            self.transport.loseConnection()
        else:
            self.transport.loseConnection()

    def connectionLost(self, reason):
        pass

def run_diagnostics():
    host = "demo-us-eqx-01.p.c-trader.com"
    port = 5211
    password = "YVxs9b3fp4Y.4m$"
    
    attempts = [
        {"name": "Standard (cServer)", "sender": "demo.pepperstone.5282126", "target": "cServer", "sub": "QUOTE"},
        {"name": "Caps (CSERVER)", "sender": "demo.pepperstone.5282126", "target": "CSERVER", "sub": "QUOTE"},
        {"name": "No SubID (cServer)", "sender": "demo.pepperstone.5282126", "target": "cServer", "sub": ""},
        {"name": "Trade Port (5212)", "sender": "demo.pepperstone.5282126", "target": "cServer", "sub": "TRADE", "port": 5212},
    ]

    def run_next(index):
        if index >= len(attempts):
            print("\n--- Diagnostics Finished ---")
            reactor.stop()
            return
        
        a = attempts[index]
        p = a.get("port", 5211)
        
        factory = protocol.ClientFactory()
        factory.protocol = lambda: DiagnosticFIX(a["sender"], a["target"], password, a["sub"], a["name"])
        
        reactor.connectSSL(host, p, factory, ssl.ClientContextFactory())
        reactor.callLater(3, run_next, index + 1)

    run_next(0)
    reactor.run()

if __name__ == "__main__":
    run_diagnostics()
