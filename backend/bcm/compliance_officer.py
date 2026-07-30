import sys
import os

BCM_DIR = os.path.dirname(os.path.abspath(__file__))
if BCM_DIR not in sys.path:
    sys.path.insert(0, BCM_DIR)

import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Hardcoded Fund Mandates (Risk Limits)
MAX_RISK_PER_TRADE_USD = 500  # Example max risk
ALLOWED_SYMBOLS = ["BTC", "GBPUSD", "US500", "BRENT"]
MAX_VOLUME_MULTIPLIER = 3  # Max allowed volume vs base volume

class ComplianceOfficer:
    def __init__(self):
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.model = "deepseek/deepseek-chat" # Fast and strict for compliance
        
    def check_hard_limits(self, symbol, action, volume, base_volume, sl, tp, entry_price):
        """Rule-based compliance checks that cannot be overridden by AI."""
        if symbol not in ALLOWED_SYMBOLS:
            return False, f"HARD LIMIT: Symbol {symbol} is not on the approved list."
        if action not in ["buy", "sell", "wait"]:
            return False, f"HARD LIMIT: Invalid action {action}."
        if action != "wait":
            if not sl or not tp:
                return False, "HARD LIMIT: All trades must have a Stop Loss and Take Profit."
            if float(volume) > base_volume * MAX_VOLUME_MULTIPLIER:
                return False, f"HARD LIMIT: Volume {volume} exceeds max allowed multiplier."
            
            # Rough distance check
            if action == "buy" and float(sl) >= entry_price:
                return False, "HARD LIMIT: Buy order SL must be below entry price."
            if action == "sell" and float(sl) <= entry_price:
                return False, "HARD LIMIT: Sell order SL must be above entry price."
                
        return True, "Hard limits passed."

    def llm_sanity_check(self, md_decision, risk_report):
        """AI-based sanity check to catch logical errors or hallucinations in the MD's decision."""
        prompt = f"""
        You are the Chief Compliance Officer (CCO) at Berezini Capital Management.
        Your job is to review the Managing Director's (MD) proposed trade and the Risk Manager's report.
        You must approve or reject the trade based on logic, consistency, and fund safety.
        
        Risk Manager Report: {risk_report}
        MD Decision: {md_decision}
        
        Respond with ONLY a JSON object:
        {{"approved": true/false, "reason": "Short explanation"}}
        """
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "messages": [{"role": "system", "content": f"You are a strict Compliance Officer. Current Time: {current_time}"}, {"role": "user", "content": prompt}]}
        
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
            content = r.json()['choices'][0]['message']['content']
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            data = json.loads(content)
            return data.get("approved", False), data.get("reason", "Failed to parse compliance decision.")
        except Exception as e:
            return False, f"Compliance Agent System Error: {e}"

    def audit_trade(self, symbol, action, volume, base_volume, sl, tp, entry_price, md_decision, risk_report):
        """Main entry point for compliance check."""
        # 1. Check Hard Limits
        passed, reason = self.check_hard_limits(symbol, action, volume, base_volume, sl, tp, entry_price)
        if not passed:
            return False, reason
            
        # If it's just a wait, no need for deep LLM compliance check
        if action == "wait":
            return True, "Action is WAIT. Approved."
            
        # 2. Check Logical Consistency via LLM
        llm_passed, llm_reason = self.llm_sanity_check(md_decision, risk_report)
        if not llm_passed:
            return False, f"LLM Sanity Check Failed: {llm_reason}"
            
        return True, "Compliance Approved."
