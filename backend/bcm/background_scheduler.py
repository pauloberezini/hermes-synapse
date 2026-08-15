import time
import subprocess
import os
from datetime import datetime

"""
Stage 6 Architecture: 3-Layer Automation
----------------------------------------
Layer 1: Scheduled (Cron jobs in backend/scheduler.py & Session polls in this file)
Layer 2: Event-Driven (Price alerts via price_monitor.py & Webhook FIX events)
Layer 3: Parallel Workers (Asyncio background dispatch of autonomous_trader across symbols)
"""

# Path to the scheduler script
SCHEDULER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_scheduler.py")

def run_loop():
    print(f"[{datetime.now()}] 🛡️ Pepperstone Session Scheduler Service Started.")
    print("This service will check for session openings every minute.")
    
    iteration = 0
    while True:
        iteration += 1
        try:
            # Run the check
            # We use check_call to wait for it to finish
            subprocess.call(["python3", SCHEDULER_SCRIPT])
        except Exception as e:
            print(f"Error in scheduler loop: {e}")
            
        # Run self-learning pipeline every 60 iterations (approx 1 hour)
        if iteration % 60 == 0:
            try:
                from backend.bcm.self_learning_pipeline import SelfLearningEngine
                print(f"[{datetime.now()}] 🧠 Triggering Self-Learning Pipeline...")
                engine = SelfLearningEngine()
                res = engine.analyze_closed_trades()
                print(f"[{datetime.now()}] 🧠 Self-Learning Result: {res}")
            except Exception as e:
                print(f"Error in self-learning pipeline: {e}")
        
        # Wait for 1 minute (60 seconds)
        time.sleep(60)

if __name__ == "__main__":
    run_loop()
