# services/conversions.py
from models.ferr import FERR
from models.frv import FRV

def convert_reer_to_ferr(accounts: dict, owner_age: int, use_spousal_age: bool = False):
    """Convertit REER -> FERR à 71 ans (si compte REER existe)."""
    if "REER" in accounts and accounts["REER"].balance > 0:
        reer = accounts.pop("REER")
        accounts["FERR"] = FERR(name="FERR", balance=reer.balance, annual_return=reer.annual_return,
                                owner_age=owner_age, use_spousal_age=use_spousal_age)

def convert_cri_to_frv(accounts: dict, owner_age: int, province: str = "QC"):
    """Convertit CRI -> FRV à la retraite (si compte CRI existe)."""
    if "CRI" in accounts and accounts["CRI"].balance > 0:
        cri = accounts.pop("CRI")
        accounts["FRV"] = FRV(name="FRV", balance=cri.balance, annual_return=cri.annual_return,
                              owner_age=owner_age, province=province)