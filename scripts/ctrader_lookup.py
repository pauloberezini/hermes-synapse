#!/usr/bin/env python3
import asyncio
import os
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.bcm.openapi_client import CTraderOpenApiClient, pb2
from dotenv import load_dotenv

async def lookup(symbol_name: str):
    load_dotenv()
    client = CTraderOpenApiClient()
    
    # 1. Connect and auth
    if not await client.connect():
        print("❌ Could not connect to cTrader OpenAPI server.")
        return

    try:
        if not await client.authorize_app():
            print("App Auth Failed")
            return
            
        if not await client.authorize_account():
            print("Account Auth Failed")
            return

        # 2. Get symbol list to find ID by name
        req = pb2.ProtoOASymbolsListReq()
        req.ctidTraderAccountId = int(client.ctid)
        res_msg = await client.send_message(2114, req)
        
        res = pb2.ProtoOASymbolsListRes()
        res.ParseFromString(res_msg.payload)
        
        target_light_sym = None
        for sym in res.symbol:
            if sym.symbolName.upper() == symbol_name.upper():
                target_light_sym = sym
                break
                
        if not target_light_sym:
            print(f"Symbol '{symbol_name}' not found on broker.")
            return
            
        print(f"Found {symbol_name} with ID: {target_light_sym.symbolId}")
        
        # 3. Get detailed info
        req_info = pb2.ProtoOASymbolByIdReq()
        req_info.ctidTraderAccountId = int(client.ctid)
        req_info.symbolId.append(target_light_sym.symbolId)
        
        info_msg = await client.send_message(2116, req_info)
        info_res = pb2.ProtoOASymbolByIdRes()
        info_res.ParseFromString(info_msg.payload)
        
        for sym in info_res.symbol:
            print(f"--- Symbol Details for {target_light_sym.symbolName} (ID: {sym.symbolId}) ---")
            print(f"Digits (Precision): {sym.digits}")
            print(f"Pip Position: {sym.pipPosition}")
            print(f"Min Volume (Units): {sym.minVolume / 100.0}")
            print(f"Max Volume (Units): {sym.maxVolume / 100.0}")
            print(f"Step Volume (Units): {sym.stepVolume / 100.0}")
            print(f"Lot Size: {sym.lotSize / 100.0}")
            print(f"Base Asset ID: {target_light_sym.baseAssetId}")
            print(f"Quote Asset ID: {target_light_sym.quoteAssetId}")
            print(f"Symbol Category ID: {target_light_sym.symbolCategoryId}")
    finally:
        await client.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 ctrader_lookup.py <SYMBOL_NAME> (e.g. GBPUSD or XAGUSD)")
        sys.exit(1)
    
    asyncio.run(lookup(sys.argv[1]))
