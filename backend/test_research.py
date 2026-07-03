import os
import sys
import asyncio
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from dotenv import load_dotenv
load_dotenv()

from backend.subagents import ResearchAgent

async def main():
    api_key = os.getenv("OPENROUTER_API_KEY")
    # Simulate a typical Gemini model
    model = "google/gemini-2.5-pro"
    
    agent = ResearchAgent(api_key, model)
    instructions = "1. Найди расписание вечерних футбольных матчей на 21 июня 2026 года. 2. Для найденных матчей собери коэффициенты ставок от нескольких букмекерских контор. 3. Найди в сети аналитические материалы или прогнозы, определяющие 'валуйные ставки' (value bets) на эти матчи."
    
    print("--- RUNNING ResearchAgent.run ---")
    res = await agent.run(instructions)
    print("--- RESULT ---")
    print(res)

asyncio.run(main())
