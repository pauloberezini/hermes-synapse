import sys
import os
import time
import uuid
from datetime import datetime
from dotenv import load_dotenv

# Load .env file automatically
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

import simplefix
from twisted.internet import reactor, ssl, protocol

class PepperstoneTrader(protocol.Protocol):
    def __init__(self, sender, target, password):
        self.sender = sender
        self.target = target
        self.password = password
        self.msg_seq_num = 1
        self.logged_in = False
        # Pending SL/TP to apply after market order fills
        self.pending_cl_ord_id = None
        self.pending_symbol = None
        self.pending_side = None
        self.pending_volume = None
        self.pending_sl = None
        self.pending_tp = None

    def send_msg(self, body_msg):
        msg = simplefix.FixMessage()
        msg.append_pair(8, "FIX.4.4")
        msg.append_pair(35, body_msg.get(35))
        msg.append_pair(49, self.sender)
        msg.append_pair(56, self.target)
        msg.append_pair(34, self.msg_seq_num)
        msg.append_pair(52, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
        msg.append_pair(57, "TRADE") # Always TRADE for this client
        
        for tag, value in body_msg:
            if tag not in [8, 9, 35, 49, 56, 34, 52, 57]:
                msg.append_pair(tag, value)
        
        raw = msg.encode()
        print(f"SEND: {raw.decode('ascii').replace(chr(1), '|')}", flush=True)
        self.transport.write(raw)
        self.msg_seq_num += 1

    def connectionMade(self):
        print(f"Connected to TRADE server. Logging in...", flush=True)
        msg = simplefix.FixMessage()
        msg.append_pair(35, "A")
        msg.append_pair(98, 0)
        msg.append_pair(108, 30)
        msg.append_pair(141, "Y")
        msg.append_pair(553, self.sender.split('.')[-1])
        msg.append_pair(554, self.password)
        self.send_msg(msg)

    def dataReceived(self, data):
        parser = simplefix.FixParser()
        parser.append_buffer(data)
        msg = parser.get_message()
        while msg:
            raw = msg.encode().decode('ascii', errors='ignore')
            msg_type = msg.get(35).decode('ascii')
            print(f"RECV [{msg_type}]: {raw.replace(chr(1), '|')}", flush=True)
            
            if msg_type == "A":
                print("✅ TRADE Logon Successful!", flush=True)
                self.logged_in = True
                # Here we can trigger the action passed via CLI
                self.on_ready()
            elif msg_type == "8": # Execution Report
                status = msg.get(39).decode('ascii')
                fill_price = msg.get(6).decode('ascii') if msg.get(6) else ""
                order_id = msg.get(37).decode('ascii') if msg.get(37) else ""
                pos_id = msg.get(721).decode('ascii') if msg.get(721) else ""
                if status == "2":  # Filled
                    print(f"✅ FILLED at {fill_price} | OrderID: {order_id} | PosID: {pos_id}", flush=True)
                    if (self.pending_sl or self.pending_tp) and pos_id:
                        # Step 2: Set SL/TP via separate orders linked to PosID (721)
                        self._apply_sltp(pos_id)
                    else:
                        reactor.callLater(1, reactor.stop)
                elif status == "0":
                    print(f"🟡 Order accepted by broker (pending fill)...", flush=True)
                elif status == "5": # Replaced
                    print(f"✅ ORDER REPLACED (SL/TP Applied) | OrderID: {order_id}", flush=True)
                    reactor.callLater(1, reactor.stop)
                elif status in ["4", "8"]:
                    text = msg.get(58).decode('ascii') if msg.get(58) else ""
                    print(f"❌ Order {('cancelled' if status=='4' else 'rejected')}: {text}", flush=True)
                    reactor.callLater(1, reactor.stop)
            elif msg_type == "3": # Session Level Reject
                reject_reason = msg.get(58).decode('ascii') if msg.get(58) else 'Unknown'
                print(f"❌ SESSION REJECT: {reject_reason}", flush=True)
                reactor.callLater(1, reactor.stop)
            elif msg_type == "9": # Order Cancel Reject
                print(f"❌ SL/TP modify rejected: {msg.get(58).decode('ascii') if msg.get(58) else ''}", flush=True)
                reactor.callLater(1, reactor.stop)
                
            msg = parser.get_message()

    def on_ready(self):
        # This will be overridden by the factory to perform specific actions
        pass

    def place_order(self, symbol_id, side, volume, stop_loss=None, take_profit=None):
        """
        Step 1: Place clean market order. Step 2: Apply SL/TP via 35=G after fill.
        side: '1' for Buy, '2' for Sell
        """
        cl_ord_id = str(uuid.uuid4())[:20]
        # Store SL/TP to apply after fill confirmation
        self.pending_cl_ord_id = cl_ord_id
        self.pending_symbol = symbol_id
        self.pending_side = side
        self.pending_volume = volume
        self.pending_sl = stop_loss
        self.pending_tp = take_profit
        
        print(f"🚀 Placing {('BUY' if side=='1' else 'SELL')} | Symbol:{symbol_id} Vol:{volume} SL:{stop_loss} TP:{take_profit}", flush=True)
        
        msg = simplefix.FixMessage()
        msg.append_pair(35, "D") # NewOrderSingle
        msg.append_pair(11, cl_ord_id)
        msg.append_pair(55, symbol_id)
        msg.append_pair(54, side)
        msg.append_pair(60, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
        msg.append_pair(38, volume)
        msg.append_pair(40, "1") # Market
        # SL/TP sent AFTER fill via _apply_sltp() — cTrader rejects them in NewOrderSingle
        self.send_msg(msg)

    def _apply_sltp(self, pos_id):
        """Step 2: Send Limit and Stop orders linked to PositionID (721) for TP and SL."""
        print(f"🔒 Applying SL/TP via separate orders to PosID:{pos_id} | SL:{self.pending_sl} TP:{self.pending_tp}", flush=True)
        offset_side = "2" if self.pending_side == "1" else "1"
        
        # Stop Loss (Stop Order)
        if self.pending_sl:
            msg_sl = simplefix.FixMessage()
            msg_sl.append_pair(35, "D")
            msg_sl.append_pair(11, str(uuid.uuid4())[:20])
            msg_sl.append_pair(55, self.pending_symbol)
            msg_sl.append_pair(54, offset_side)
            msg_sl.append_pair(60, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg_sl.append_pair(38, self.pending_volume)
            msg_sl.append_pair(40, "3") # Stop
            msg_sl.append_pair(99, self.pending_sl) # StopPx
            msg_sl.append_pair(721, pos_id) # Link to Position
            self.send_msg(msg_sl)
            
        # Take Profit (Limit Order)
        if self.pending_tp:
            msg_tp = simplefix.FixMessage()
            msg_tp.append_pair(35, "D")
            msg_tp.append_pair(11, str(uuid.uuid4())[:20])
            msg_tp.append_pair(55, self.pending_symbol)
            msg_tp.append_pair(54, offset_side)
            msg_tp.append_pair(60, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg_tp.append_pair(38, self.pending_volume)
            msg_tp.append_pair(40, "2") # Limit
            msg_tp.append_pair(44, self.pending_tp) # Price
            msg_tp.append_pair(721, pos_id) # Link to Position
            self.send_msg(msg_tp)
            
        reactor.callLater(3, reactor.stop)

    def modify_order(self, pos_id, symbol_id, side, volume, stop_loss=None, take_profit=None):
        """Set SL/TP on an existing position. Requires actual PositionID (tag 721)."""
        print(f"🔒 Setting SL/TP via separate orders to PosID:{pos_id} | SL:{stop_loss} TP:{take_profit}", flush=True)
        offset_side = "2" if str(side) == "1" else "1"
        
        if stop_loss:
            msg_sl = simplefix.FixMessage()
            msg_sl.append_pair(35, "D")
            msg_sl.append_pair(11, str(uuid.uuid4())[:20])
            msg_sl.append_pair(55, symbol_id)
            msg_sl.append_pair(54, offset_side)
            msg_sl.append_pair(60, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg_sl.append_pair(38, volume)
            msg_sl.append_pair(40, "3") # Stop
            msg_sl.append_pair(99, stop_loss) # StopPx
            msg_sl.append_pair(721, pos_id) # Link to Position
            self.send_msg(msg_sl)
            
        if take_profit:
            msg_tp = simplefix.FixMessage()
            msg_tp.append_pair(35, "D")
            msg_tp.append_pair(11, str(uuid.uuid4())[:20])
            msg_tp.append_pair(55, symbol_id)
            msg_tp.append_pair(54, offset_side)
            msg_tp.append_pair(60, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg_tp.append_pair(38, volume)
            msg_tp.append_pair(40, "2") # Limit
            msg_tp.append_pair(44, take_profit) # Price
            msg_tp.append_pair(721, pos_id) # Link to Position
            self.send_msg(msg_tp)
            
        reactor.callLater(3, reactor.stop)

    def close_order(self, order_id, symbol_id, side, volume):
        """Close specific position by sending NewOrderSingle (35=D) linked to PosID (721)"""
        cl_ord_id = str(uuid.uuid4())[:20]
        offset_side = "2" if str(side) in ("1", "BUY", "buy") else "1"
        print(f"📉 Closing position {order_id} (Symbol ID:{symbol_id}) with offsetting {('BUY' if offset_side=='1' else 'SELL')}", flush=True)
        
        msg = simplefix.FixMessage()
        msg.append_pair(35, "D") # NewOrderSingle
        msg.append_pair(11, cl_ord_id)
        msg.append_pair(55, symbol_id)
        msg.append_pair(54, offset_side)
        msg.append_pair(60, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
        msg.append_pair(38, volume)
        msg.append_pair(40, "1") # Market
        if order_id and str(order_id).strip() != "1":
            msg.append_pair(721, str(order_id).strip()) # Explicit Position ID to close
        self.send_msg(msg)

    def place_limit_order(self, symbol_id, side, volume, price):
        """Limit Order (35=D, OrdType=2)"""
        cl_ord_id = str(uuid.uuid4())[:20]
        msg = simplefix.FixMessage()
        msg.append_pair(35, "D")
        msg.append_pair(11, cl_ord_id)
        msg.append_pair(55, symbol_id)
        msg.append_pair(54, side)
        msg.append_pair(60, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
        msg.append_pair(38, volume)
        msg.append_pair(40, "2") # Limit
        msg.append_pair(44, price) # Price
        self.send_msg(msg)

    def place_stop_order(self, symbol_id, side, volume, stop_price):
        """Stop Order (35=D, OrdType=3)"""
        cl_ord_id = str(uuid.uuid4())[:20]
        msg = simplefix.FixMessage()
        msg.append_pair(35, "D")
        msg.append_pair(11, cl_ord_id)
        msg.append_pair(55, symbol_id)
        msg.append_pair(54, side)
        msg.append_pair(60, datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
        msg.append_pair(38, volume)
        msg.append_pair(40, "3") # Stop
        msg.append_pair(99, stop_price) # StopPx
        self.send_msg(msg)

def run_trade_action(action, **kwargs):
    sender = os.environ.get("SENDER", "demo.pepperstone.5282126")
    target = os.environ.get("TARGET", "cServer")
    password = os.environ.get("PASSWORD")
    host = os.environ.get("TRADE_HOST", "demo-us-eqx-01.p.c-trader.com")
    port = int(os.environ.get("TRADE_PORT", "5212"))

    class TradeFactory(protocol.ClientFactory):
        def buildProtocol(self, addr):
            p = PepperstoneTrader(sender, target, password)
            if action == "place":
                p.on_ready = lambda: p.place_order(kwargs['symbol'], kwargs['side'], kwargs['volume'], kwargs.get('sl'), kwargs.get('tp'))
            elif action == "close":
                p.on_ready = lambda: p.close_order(kwargs['order_id'], kwargs['symbol'], kwargs['side'], kwargs['volume'])
            elif action == "limit":
                p.on_ready = lambda: p.place_limit_order(kwargs['symbol'], kwargs['side'], kwargs['volume'], kwargs['price'])
            elif action == "stop":
                p.on_ready = lambda: p.place_stop_order(kwargs['symbol'], kwargs['side'], kwargs['volume'], kwargs['price'])
            elif action == "modify":
                p.on_ready = lambda: p.modify_order(kwargs['order_id'], kwargs['symbol'], kwargs['side'], kwargs['volume'], kwargs.get('sl'), kwargs.get('tp'))
            return p

    def connectionFailed(self, reason):
        print(f"❌ Connection Failed: {reason.getErrorMessage()}", flush=True)
        if reactor.running: reactor.stop()

    def connectionLost(self, reason):
        print(f"📉 Connection Lost: {reason.getErrorMessage()}", flush=True)
        if reactor.running: reactor.stop()

    reactor.connectSSL(host, port, TradeFactory(), ssl.ClientContextFactory())
    # Add absolute timeout of 60 seconds
    reactor.callLater(60, lambda: (print("⏰ FIX Operation Timeout", flush=True), reactor.stop()) if reactor.running else None)
    reactor.run()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 pepperstone_trader.py <action> ...")
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "place":
        # python3 pepperstone_trader.py place <symbol> <side> <vol> [sl] [tp]
        run_trade_action("place", 
                         symbol=sys.argv[2], 
                         side=sys.argv[3], 
                         volume=sys.argv[4],
                         sl=sys.argv[5] if len(sys.argv)>5 else None,
                         tp=sys.argv[6] if len(sys.argv)>6 else None)
    elif cmd == "limit":
        run_trade_action("limit", symbol=sys.argv[2], side=sys.argv[3], volume=sys.argv[4], price=sys.argv[5])
    elif cmd == "stop":
        run_trade_action("stop", symbol=sys.argv[2], side=sys.argv[3], volume=sys.argv[4], price=sys.argv[5])
    elif cmd == "close":
        run_trade_action("close", order_id=sys.argv[2], symbol=sys.argv[3], side=sys.argv[4], volume=sys.argv[5])
    elif cmd == "modify":
        run_trade_action("modify", order_id=sys.argv[2], symbol=sys.argv[3], side=sys.argv[4], volume=sys.argv[5], sl=sys.argv[6] if len(sys.argv)>6 else None, tp=sys.argv[7] if len(sys.argv)>7 else None)
