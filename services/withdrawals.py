# services/withdrawals.py
from typing import Dict

def apply_ferr_mandatory_withdrawal(accounts: Dict[str, object], person_age: int, spouse_age: int = None, use_spousal_age: bool = False) -> float:
    ferr = accounts.get("FERR")
    if ferr is None:
        return 0.0
    ferr.owner_age = person_age
    ferr.use_spousal_age = use_spousal_age
    ferr.spouse_age = spouse_age
    amount = ferr.mandatory_withdrawal()
    return ferr.withdraw(amount)

def apply_frv_min_withdrawal(accounts: Dict[str, object], person_age: int) -> float:
    frv = accounts.get("FRV")
    if frv is None:
        return 0.0
    frv.owner_age = person_age
    amount = frv.min_withdrawal()
    return frv.withdraw(amount)