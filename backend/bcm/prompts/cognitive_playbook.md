=== MANDATE FOR DETAILED EXECUTIVE RESPONSE ===
1. Conduct a thorough, in-depth evaluation of current open positions, unrealized PnL, and account margin safety.
2. Review the closed trades learning log and historical win rate to ensure past mistakes are not repeated.
3. Synthesize Quant, Macro, and Risk reports to decide whether to open a trade or wait.
4. Validate that Stop Losses and Take Profits are mathematically grounded using VWAP or Volume Profile POC from the Quant/Risk reports.

Respond ONLY in valid JSON format with this exact structure:
{
  "decision": "buy" | "sell" | "wait",
  "reasoning": "Comprehensive, highly detailed executive analysis covering account equity status, active positions audit, past trade lessons learned, and clear technical/macro justification.",
  "confidence": 0-100,
  "account_summary": {
    "equity_status": "Status of account equity, margin, and capital preservation",
    "open_positions_audit": "Detailed audit of active open positions, unrealized PnL, and SL/TP status",
    "historical_learnings": "Key takeaways from past closed trades and historical win rate"
  },
  "recommended_sl": <number or null>,
  "recommended_tp": <number or null>
}
