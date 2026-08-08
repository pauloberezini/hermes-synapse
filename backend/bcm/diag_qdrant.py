import sys
sys.path.append("./skills/pepperstone-trader/scripts/")
from memory_manager import BCMMemory
import json

try:
    print("--- Diagnostic Start ---")
    memory = BCMMemory()
    print(f"Memory Type: {type(memory)}")
    print(f"QClient Type: {type(memory.qclient)}")
    print(f"Has search: {hasattr(memory.qclient, 'search')}")
    print(f"Has query_points: {hasattr(memory.qclient, 'query_points')}")
    
    dummy_data = {"rsi": 50, "remizov_shift": 0}
    exp = memory.get_similar_experience(dummy_data)
    print(f"Search Result: {exp}")
    print("--- Diagnostic End ---")
except Exception as e:
    print(f"DIAGNOSTIC FAILED: {e}")
    import traceback
    traceback.print_exc()
