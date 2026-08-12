import sys
import os

BCM_DIR = os.path.dirname(os.path.abspath(__file__))
if BCM_DIR not in sys.path:
    sys.path.insert(0, BCM_DIR)

import json
import requests
from datetime import datetime
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Hardcoded Fund Mandates (Risk Limits)
MAX_RISK_PER_TRADE_USD = 500  # Example max risk
ALLOWED_SYMBOLS = ["BTC", "GBPUSD", "US500", "BRENT", "GOLD", "XAGUSD"]
ALLOWED_BYBIT_BASE_COINS = ["BTC", "ETH"]  # Bybit options base coins
BYBIT_OPTIONS_MAX_LOSS_PCT = 0.02  # Max 2% of equity per options trade
BYBIT_OPTIONS_MAX_LEGS = 2  # Max legs in a single spread
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
            r = requests.post(f"{os.environ.get('LLM_API_BASE', 'https://openrouter.ai/api/v1').rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=30)
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

    def audit_options_trade(
        self,
        base_coin: str,
        strategy: str,
        max_loss_usd: float,
        net_credit_usd: float,
        account_equity: float,
        num_legs: int = 2,
        reasoning: str = ""
    ):
        """Compliance check specifically for Bybit options/spread trades.
        
        Returns:
            (approved: bool, reason: str)
        """
        # 1. Hard limit: base coin must be on approved list
        if base_coin.upper() not in ALLOWED_BYBIT_BASE_COINS:
            return False, f"HARD LIMIT: Base coin {base_coin} is not on approved Bybit options list ({ALLOWED_BYBIT_BASE_COINS})."

        # 2. Hard limit: only recognised strategies
        allowed_strategies = ["put_spread", "call_spread", "iron_condor", "naked_put", "naked_call"]
        if strategy not in allowed_strategies:
            return False, f"HARD LIMIT: Strategy '{strategy}' is not recognised. Allowed: {allowed_strategies}."

        # 3. Hard limit: max loss must not exceed 2% of equity
        if account_equity > 0:
            max_loss_pct = max_loss_usd / account_equity
            if max_loss_pct > BYBIT_OPTIONS_MAX_LOSS_PCT:
                return False, (
                    f"HARD LIMIT: Max loss ${max_loss_usd:.2f} = {max_loss_pct:.1%} of equity "
                    f"(${account_equity:,.2f}) exceeds {BYBIT_OPTIONS_MAX_LOSS_PCT:.0%} cap."
                )

        # 4. Hard limit: sanity check — credit trade must actually receive credit
        if net_credit_usd < 0:
            return False, f"HARD LIMIT: Net credit is negative (${net_credit_usd:.2f}). Debit spreads not allowed under this mandate."

        # 5. Hard limit: leg count
        if num_legs > BYBIT_OPTIONS_MAX_LEGS:
            return False, f"HARD LIMIT: Trade has {num_legs} legs, max allowed is {BYBIT_OPTIONS_MAX_LEGS}."

        # 6. Naked options: extra check — require explicit approval
        if strategy in ("naked_put", "naked_call"):
            return False, "HARD LIMIT: Naked options are prohibited under BCM mandate. Use a spread strategy."

        return True, (
            f"Compliance Approved. Strategy: {strategy} | Max Loss: ${max_loss_usd:.2f} "
            f"({max_loss_usd / account_equity:.1%} of equity) | Net Credit: ${net_credit_usd:.2f}."
        )
