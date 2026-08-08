import sys
import os
import time
from datetime import datetime
import simplefix
from twisted.internet import reactor, ssl, protocol

class PepperstoneFIX(protocol.Protocol):
    def __init__(self, sender_comp_id, target_comp_id, password, sub_id):
        self.sender_comp_id = sender_comp_id
        self.target_comp_id = target_comp_id
        self.password = password
        self.sub_id = sub_id
        self.msg_seq_num = 1

    def send_msg(self, body_msg):
        """Prepare and send a simplefix message with correct header order."""
        msg = simplefix.FixMessage()
        
        # Header (Tag 8 must be first, Tag 9 is added by encode())
        msg.append_pair(8, "FIX.4.4")
        msg.append_pair(35, body_msg.get(35)) # Tag 35 must be early
        msg.append_pair(49, self.sender_comp_id)
        msg.append_pair(56, self.target_comp_id)
        msg.append_pair(34, self.msg_seq_num)
        msg.append_pair(52, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
        if self.sub_id:
            msg.append_pair(57, self.sub_id)
            
        # Body
        for tag, value in body_msg:
            if tag not in [8, 9, 35, 49, 56, 34, 52, 57]:
                msg.append_pair(tag, value)
        
        raw = msg.encode()
        print(f"SEND: {raw.decode('ascii').replace(chr(1), '|')}", flush=True)
        self.transport.write(raw)
        self.msg_seq_num += 1

    def subscribe_market_data(self, symbols):
        """Send MarketDataRequest (35=V) for multiple symbols."""
        print(f"Subscribing to: {', '.join(symbols)}", flush=True)
        msg = simplefix.FixMessage()
        msg.append_pair(35, "V")
        msg.append_pair(262, f"REQ_{int(time.time())}") # MDReqID
        msg.append_pair(263, 1) # SubscriptionRequestType: Snapshot + Updates
        msg.append_pair(264, 1) # MarketDepth: Top of Book
        
        msg.append_pair(267, 2) # NoMDEntryTypes
        msg.append_pair(269, 0) # Bid
        msg.append_pair(269, 1) # Offer
        
        msg.append_pair(146, len(symbols)) # NoRelatedSym
        for symbol in symbols:
            msg.append_pair(55, symbol)
            
        self.send_msg(msg)

    def connectionMade(self):
        print(f"Connected to {self.target_comp_id}. Sending Logon...", flush=True)
        msg = simplefix.FixMessage()
        msg.append_pair(35, "A") # Logon
        msg.append_pair(98, 0)   # EncryptMethod
        msg.append_pair(108, 30) # HeartBtInt
        msg.append_pair(141, "Y") # ResetSeqNumFlag
        msg.append_pair(553, self.sender_comp_id.split('.')[-1]) # Username
        msg.append_pair(554, self.password) # Password
        self.send_msg(msg)

    def dataReceived(self, data):
        # Parse incoming data
        parser = simplefix.FixParser()
        parser.append_buffer(data)
        msg = parser.get_message()
        
        while msg:
            raw = msg.encode().decode('ascii', errors='ignore')
            print(f"RECV: {raw.replace(chr(1), '|')}", flush=True)
            
            msg_type = msg.get(35).decode('ascii')
            if msg_type == "A":
                print("✅ Logon Successful!", flush=True)
                # Using IDs from user screenshots: GBPUSD=2, US500=10013, Brent-F=11045, BTCUSD=10028
                self.subscribe_market_data(["2", "10013", "11045", "10028"])
                reactor.callLater(30, self.send_heartbeat)
            elif msg_type == "W": # Market Data Snapshot
                symbol_id = msg.get(55).decode('ascii')
                # Map IDs back to names for readability
                names = {"2": "GBPUSD", "10013": "US500", "11045": "BRENT", "10028": "BTCUSD"}
                name = names.get(symbol_id, f"ID:{symbol_id}")
                print(f"📈 DATA {name}: {raw.replace(chr(1), '|')}", flush=True)
            elif msg_type == "j": # Reject
                print(f"❌ REJECT: {msg.get(58).decode('ascii') if msg.get(58) else 'Unknown reason'}", flush=True)
            elif msg_type == "0":
                print("Heartbeat received.", flush=True)
            elif msg_type == "5":
                print(f"Logout received: {msg.get(58).decode('ascii') if msg.get(58) else 'No reason'}", flush=True)
                self.transport.loseConnection()
            elif msg_type == "1": # Test Request
                self.send_heartbeat()
                
            msg = parser.get_message()

    def send_heartbeat(self):
        msg = simplefix.FixMessage()
        msg.append_pair(35, "0")
        self.send_msg(msg)
        reactor.callLater(30, self.send_heartbeat)

    def connectionLost(self, reason):
        print("Connection lost:", reason.getErrorMessage(), flush=True)
        if reactor.running:
            reactor.stop()

def run_client():
    host = os.environ.get("PRICE_HOST", "demo-us-eqx-01.p.c-trader.com")
    port = int(os.environ.get("PRICE_PORT", "5211"))
    sender = os.environ.get("SENDER", "demo.pepperstone.5282126")
    target = os.environ.get("TARGET", "cServer")
    subid = os.environ.get("QUOTE_SUBID", "QUOTE")
    password = os.environ.get("PASSWORD", "password_here")
    
    print(f"Starting Pepperstone FIX Client (simplefix) on {host}:{port}...", flush=True)
    
    factory = protocol.ClientFactory()
    factory.protocol = lambda: PepperstoneFIX(sender, target, password, subid)
    
    # Try SSL first
    reactor.connectSSL(host, port, factory, ssl.ClientContextFactory())
    reactor.run()

if __name__ == "__main__":
    run_client()
