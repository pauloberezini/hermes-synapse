import asyncio
import ssl
import struct
import sys
import os
import json
import uuid
import time


# Add openapi directory to path to import pb2 files correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../openapi')))
import OpenApiCommonMessages_pb2 as common_pb2
import OpenApiMessages_pb2 as pb2



class CTraderOpenApiClient:
    def __init__(self, host='demo.ctraderapi.com', port=5035):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.client_id = os.getenv("CTRADER_CLIENT_ID", "")
        self.client_secret = os.getenv("CTRADER_CLIENT_SECRET", "")
        self.ctid = os.getenv("CTRADER_ACCOUNT_ID", "")
        self.access_token = os.getenv("CTRADER_ACCESS_TOKEN", "")
        self.pending_requests = {}
        self.is_connected = False
        
    async def connect(self):
        print(f"Connecting to {self.host}:{self.port} with TLS...")
        context = ssl.create_default_context()
        self.reader, self.writer = await asyncio.open_connection(
            self.host, self.port, ssl=context
        )
        self.is_connected = True
        print("Connected!")
        
        # Start read loop
        asyncio.create_task(self.read_loop())
        # Start heartbeat
        asyncio.create_task(self.heartbeat_loop())
        
    async def send_message(self, payload_type, payload, client_msg_id=None):
        if not client_msg_id:
            client_msg_id = str(uuid.uuid4())
            
        # Create ProtoMessage Wrapper
        proto_msg = common_pb2.ProtoMessage()
        proto_msg.payloadType = payload_type
        proto_msg.payload = payload.SerializeToString()
        proto_msg.clientMsgId = client_msg_id
        
        data = proto_msg.SerializeToString()
        # Framing: 4 bytes length + message
        length = len(data)
        framed_data = struct.pack('>I', length) + data
        
        self.writer.write(framed_data)
        await self.writer.drain()
        print(f"-> Sent message type {payload_type} (id: {client_msg_id})")
        
        # Return a future for the response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[client_msg_id] = future
        return await future

    async def read_loop(self):
        while self.is_connected:
            try:
                # Read length header (4 bytes)
                length_data = await self.reader.readexactly(4)
                length = struct.unpack('>I', length_data)[0]
                
                # Read payload
                data = await self.reader.readexactly(length)
                proto_msg = common_pb2.ProtoMessage()
                proto_msg.ParseFromString(data)
                
                self.handle_message(proto_msg)
            except asyncio.IncompleteReadError:
                print("Connection closed by server.")
                self.is_connected = False
                break
            except Exception as e:
                print(f"Error reading from socket: {e}")
                self.is_connected = False
                break

    def handle_message(self, msg):
        # Resolve pending request if we have a client_msg_id
        if msg.clientMsgId and msg.clientMsgId in self.pending_requests:
            self.pending_requests[msg.clientMsgId].set_result(msg)
            del self.pending_requests[msg.clientMsgId]
        
        if msg.payloadType == 51: # PROTO_HEARTBEAT_EVENT
            pass # Ignore heartbeat logs to reduce spam
        elif msg.payloadType == 2126: # PROTO_OA_EXECUTION_EVENT
            event = pb2.ProtoOAExecutionEvent()
            event.ParseFromString(msg.payload)
            print(f"<- Execution Event: Type={event.executionType}, Order={event.order.orderId if event.HasField('order') else 'N/A'}, Position={event.position.positionId if event.HasField('position') else 'N/A'}")
        elif msg.payloadType == 2142: # PROTO_OA_ERROR_RES
            err = pb2.ProtoOAErrorRes()
            err.ParseFromString(msg.payload)
            print(f"<- OPEN API ERROR: {err.errorCode} - {err.description}")
        elif msg.payloadType == 2132: # PROTO_OA_ORDER_ERROR_EVENT
            err = pb2.ProtoOAOrderErrorEvent()
            err.ParseFromString(msg.payload)
            print(f"<- ORDER ERROR: {err.errorCode} - {err.description}")
        elif msg.payloadType == 50: # PROTO_ERROR_RES (Common)
            err = common_pb2.ProtoErrorRes()
            err.ParseFromString(msg.payload)
            print(f"<- COMMON ERROR: {err.errorCode} - {err.description}")
        else:
            print(f"<- Received message type: {msg.payloadType}")

    async def heartbeat_loop(self):
        while self.is_connected:
            await asyncio.sleep(25)
            # ProtoHeartbeatEvent (PayloadType = 51)
            heartbeat = common_pb2.ProtoHeartbeatEvent()
            
            # Use raw write for heartbeat to not wait for response
            proto_msg = common_pb2.ProtoMessage()
            proto_msg.payloadType = 51
            proto_msg.payload = heartbeat.SerializeToString()
            
            data = proto_msg.SerializeToString()
            length = len(data)
            framed_data = struct.pack('>I', length) + data
            
            if self.is_connected:
                self.writer.write(framed_data)
                await self.writer.drain()

    async def get_trader_details(self):
        req = pb2.ProtoOATraderReq()
        req.ctidTraderAccountId = int(self.ctid)
        
        res_msg = await self.send_message(2121, req) # PROTO_OA_TRADER_REQ = 2121
        if res_msg.payloadType == 2122: # PROTO_OA_TRADER_RES
            res = pb2.ProtoOATraderRes()
            res.ParseFromString(res_msg.payload)
            print("Trader Details:")
            for field, value in res.trader.ListFields():
                print(f"  {field.name}: {value}")
            return True
        return False

    async def authorize_app(self):
        req = pb2.ProtoOAApplicationAuthReq()
        req.clientId = self.client_id
        req.clientSecret = self.client_secret
        
        res_msg = await self.send_message(2100, req) # PROTO_OA_APPLICATION_AUTH_REQ = 2100
        if res_msg.payloadType == 2101: # PROTO_OA_APPLICATION_AUTH_RES
            print("App Authorization Successful")
            return True
        return False

    async def authorize_account(self):
        req = pb2.ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = int(self.ctid)
        req.accessToken = self.access_token
        
        res_msg = await self.send_message(2102, req) # PROTO_OA_ACCOUNT_AUTH_REQ = 2102
        if res_msg.payloadType == 2103: # PROTO_OA_ACCOUNT_AUTH_RES
            print("Account Authorization Successful")
            return True
        return False

    async def amend_position_sltp(self, position_id, stop_loss=None, take_profit=None):
        req = pb2.ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = int(self.ctid)
        req.positionId = int(position_id)
        if stop_loss is not None:
            req.stopLoss = float(stop_loss)
        if take_profit is not None:
            req.takeProfit = float(take_profit)
            
        res_msg = await self.send_message(2110, req) # PROTO_OA_AMEND_POSITION_SLTP_REQ = 2110
        if res_msg.payloadType == 2126: # PROTO_OA_EXECUTION_EVENT
            event = pb2.ProtoOAExecutionEvent()
            event.ParseFromString(res_msg.payload)
            print(f"Amend Position SL/TP Event received for Position {position_id}. ExecutionType: {event.executionType}")
            return True
        elif res_msg.payloadType == 2132: # PROTO_OA_ORDER_ERROR_EVENT
            err = pb2.ProtoOAOrderErrorEvent()
            err.ParseFromString(res_msg.payload)
            print(f"Order Error: {err.errorCode} - {err.description}")
            return False
        elif res_msg.payloadType == 2142: # PROTO_OA_ERROR_RES
            err = pb2.ProtoOAErrorRes()
            err.ParseFromString(res_msg.payload)
            print(f"OpenAPI Error: {err.errorCode} - {err.description}")
            return False
        return False

    async def list_symbols(self):
        req = pb2.ProtoOASymbolsListReq()
        req.ctidTraderAccountId = int(self.ctid)
        
        res_msg = await self.send_message(2114, req) # PROTO_OA_SYMBOLS_LIST_REQ = 2114
        if res_msg.payloadType == 2115: # PROTO_OA_SYMBOLS_LIST_RES
            res = pb2.ProtoOASymbolsListRes()
            res.ParseFromString(res_msg.payload)
            for sym in res.symbol:
                print(f"ID: {sym.symbolId}, Name: {sym.symbolName}")
            return True
        return False

    async def get_symbol_info(self, symbol_id):
        req = pb2.ProtoOASymbolByIdReq()
        req.ctidTraderAccountId = int(self.ctid)
        req.symbolId.append(int(symbol_id))
        
        res_msg = await self.send_message(2116, req) # PROTO_OA_SYMBOL_BY_ID_REQ = 2116
        if res_msg.payloadType == 2117: # PROTO_OA_SYMBOL_BY_ID_RES
            res = pb2.ProtoOASymbolByIdRes()
            res.ParseFromString(res_msg.payload)
            for sym in res.symbol:
                print(f"DEBUG SYM DIR: {dir(sym)}")
                print(f"DEBUG SYM: {sym}")
            return True
        return False

    async def get_positions(self):
        req = pb2.ProtoOAReconcileReq()
        req.ctidTraderAccountId = int(self.ctid)
        
        res_msg = await self.send_message(2124, req) # PROTO_OA_RECONCILE_REQ = 2124
        if res_msg.payloadType == 2125: # PROTO_OA_RECONCILE_RES
            res = pb2.ProtoOAReconcileRes()
            res.ParseFromString(res_msg.payload)
            print(f"Open Positions ({len(res.position)}):")
            for pos in res.position:
                sl = pos.stopLoss if pos.HasField('stopLoss') else 'None'
                tp = pos.takeProfit if pos.HasField('takeProfit') else 'None'
                side = 'BUY' if pos.tradeData.tradeSide == 1 else 'SELL'
                vol = pos.tradeData.volume / 100.0
                print(f"[{pos.positionId}] {side} Sym:{pos.tradeData.symbolId} Vol:{vol} SL:{sl} TP:{tp}")
            return True
        return False

    async def place_order(self, symbol_id, side, volume, stop_loss=None, take_profit=None):
        req = pb2.ProtoOANewOrderReq()
        req.ctidTraderAccountId = int(self.ctid)
        req.symbolId = int(symbol_id)
        req.orderType = 1 # MARKET
        
        # 1 = BUY, 2 = SELL
        req.tradeSide = 1 if str(side) == "1" else 2 
        
        # volume is passed as string like "0.01". In protocol, it is units * 100
        # If the input is in lots, it needs to be properly converted to protocol volume (cents).
        # Assuming the input volume is in actual base units. For 0.01 BTC, it's 0.01 * 100 = 1
        # For 1000 EURUSD, 1000 * 100 = 100000
        protocol_vol = int(float(volume) * 100)
        req.volume = protocol_vol
        
        if stop_loss is not None and stop_loss != "None":
            req.stopLoss = float(stop_loss)
        if take_profit is not None and take_profit != "None":
            req.takeProfit = float(take_profit)
            
        print(f"Placing Market Order: Symbol={symbol_id}, Side={'BUY' if req.tradeSide==1 else 'SELL'}, Vol={protocol_vol}, SL={stop_loss}, TP={take_profit}")
        
        # PROTO_OA_NEW_ORDER_REQ = 2106
        res_msg = await self.send_message(2106, req) 
        
        if res_msg.payloadType == 2126: # PROTO_OA_EXECUTION_EVENT
            event = pb2.ProtoOAExecutionEvent()
            event.ParseFromString(res_msg.payload)
            print(f"Order Accepted/Filled. Event Type: {event.executionType}")
            return True
        elif res_msg.payloadType == 2132: # PROTO_OA_ORDER_ERROR_EVENT
            err = pb2.ProtoOAOrderErrorEvent()
            err.ParseFromString(res_msg.payload)
            print(f"Order Error: {err.errorCode} - {err.description}")
            return False
        return False

    async def get_trader_balance(self):
        req = pb2.ProtoOATraderReq()
        req.ctidTraderAccountId = int(self.ctid)
        res_msg = await self.send_message(2111, req)
        if res_msg.payloadType == 2121:
            trader = pb2.ProtoOATraderRes()
            trader.ParseFromString(res_msg.payload)
            balance = trader.trader.balance / 100.0
            return balance
        return 0.0

    async def get_positions_list(self):
        req = pb2.ProtoOAReconcileReq()
        req.ctidTraderAccountId = int(self.ctid)
        res_msg = await self.send_message(2124, req)
        if res_msg.payloadType == 2125:
            res = pb2.ProtoOAReconcileRes()
            res.ParseFromString(res_msg.payload)
            positions = []
            for pos in res.position:
                sl = pos.stopLoss if pos.HasField('stopLoss') else None
                tp = pos.takeProfit if pos.HasField('takeProfit') else None
                side = 'BUY' if pos.tradeData.tradeSide == 1 else 'SELL'
                vol = pos.tradeData.volume / 100.0
                positions.append({
                    "positionId": pos.positionId,
                    "symbolId": pos.tradeData.symbolId,
                    "tradeSide": side,
                    "volume": vol,
                    "stopLoss": sl,
                    "takeProfit": tp
                })
            return positions
        return []

    async def close_position(self, position_id, symbol_id, side, volume):
        req = pb2.ProtoOANewOrderReq()
        req.ctidTraderAccountId = int(self.ctid)
        req.symbolId = int(symbol_id)
        req.orderType = 1 # MARKET
        req.tradeSide = 2 if str(side) == "1" else 1 # Opposite side
        req.volume = int(float(volume) * 100)
        req.positionId = int(position_id)
        
        print(f"Closing Position: ID={position_id}, Symbol={symbol_id}, Side={req.tradeSide}, Vol={req.volume}")
        res_msg = await self.send_message(2106, req)
        if res_msg.payloadType == 2126:
            return True
        return False

async def run_cli():
    if len(sys.argv) < 2:
        print("Usage: python3 openapi_client.py <action> ...")
        return
        
    client = CTraderOpenApiClient()
    await client.connect()
    
    if not await client.authorize_app():
        print("Failed app auth.")
        return
    if not client.ctid or not client.access_token:
        print("CTID or Access Token missing in .env")
        return
    if not await client.authorize_account():
        print("Failed account auth.")
        return
        
    action = sys.argv[1]
    
    try:
        if action == "place":
            # openapi_client.py place <symbol> <side> <vol> [sl] [tp]
            symbol = sys.argv[2]
            side = sys.argv[3]
            vol = sys.argv[4]
            sl = sys.argv[5] if len(sys.argv) > 5 else None
            tp = sys.argv[6] if len(sys.argv) > 6 else None
            await client.place_order(symbol, side, vol, sl, tp)
            
        elif action == "modify":
            # modify <order_id> <symbol_id> <side> <volume> <sl> <tp>
            # Actually we only need position_id, sl, tp for OpenAPI
            # But we accept the same args to be drop-in compatible, 
            # Note: order_id here should be position_id if passed from existing scripts!
            pos_id = sys.argv[2]
            sl = sys.argv[6] if len(sys.argv) > 6 else None
            tp = sys.argv[7] if len(sys.argv) > 7 else None
            await client.amend_position_sltp(pos_id, sl, tp)
            
        elif action == "close":
            # close <pos_id> <symbol_id> <side> <vol>
            pos_id = sys.argv[2]
            symbol_id = sys.argv[3]
            side = sys.argv[4]
            vol = sys.argv[5]
            await client.close_position(pos_id, symbol_id, side, vol)

        elif action == "positions":
            await client.get_positions()
        elif action == "symbol":
            symbol_id = sys.argv[2]
            await client.get_symbol_info(symbol_id)
        elif action == "list":
            await client.list_symbols()
        elif action == "trader":
            await client.get_trader_details()
    except Exception as e:
        print(f"Error during execution: {e}")
        
    # Wait a bit for execution events to arrive
    await asyncio.sleep(2)
    
    if client.writer:
        client.writer.close()
        await client.writer.wait_closed()

if __name__ == "__main__":
    asyncio.run(run_cli())
