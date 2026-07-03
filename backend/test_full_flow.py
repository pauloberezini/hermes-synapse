import os
import sys
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from backend.orchestrator import run_orchestration
from backend.agent import agent_instance

async def main():
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = agent_instance.model
    # Clean user query without date hints
    query = "Проанализируй сегодняшние вечерние матчи по футболу и найди валуйные ставки"
    print(f"Running orchestration for query: '{query}'")
    
    result = await run_orchestration(query, api_key, model, chat_id="test_flow")
    print("\n--- RESPONSE ---")
    print(result.get("response"))
    print("\n--- TRACES ---")
    for t in result.get("traces", []):
        print(f"[{t['timestamp']}] {t['agent']} - {t['action']}: {t['message']}")

asyncio.run(main())
