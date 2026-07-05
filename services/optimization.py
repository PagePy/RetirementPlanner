# services/optimization.py
def optimize_withdrawal_order(state):
    # Simple heuristic: use taxable first, then registered, CELI last
    return ["Taxable", "FERR_or_FRV", "REER", "CELI"]