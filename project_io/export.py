import csv
import json
from typing import List, Dict

def export_json(results: List[Dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def flatten_row(row: Dict) -> Dict:
    flat = {
        "year": row.get("year"),
        "age": row.get("age"),
        "retired": row.get("retired"),
        "deceased": row.get("deceased"),
        "salary": row.get("salary"),
        "RRQ": row["benefits"].get("RRQ", 0.0),
        "OAS": row["benefits"].get("OAS", 0.0),
        "SRG": row["benefits"].get("SRG", 0.0),
        "OAS_clawback": row["benefits"].get("OAS_clawback", 0.0),
        "FERR_withdrawal_mandatory": row["withdrawals"]["mandatory"].get("FERR", 0.0),
        "FRV_withdrawal_mandatory": row["withdrawals"]["mandatory"].get("FRV", 0.0),
        "FERR_withdrawal_optional": row["withdrawals"]["optional"].get("FERR", 0.0),
        "FRV_withdrawal_optional": row["withdrawals"]["optional"].get("FRV", 0.0),
        "REER_withdrawal_optional": row["withdrawals"]["optional"].get("REER", 0.0),
        "CELI_withdrawal_optional": row["withdrawals"]["optional"].get("CELI", 0.0),
        "Taxable_withdrawal_optional": row["withdrawals"]["optional"].get("Taxable", 0.0),
        "interest": row["investment_income"].get("interest", 0.0),
        "eligible_dividends": row["investment_income"].get("eligible_dividends", 0.0),
        "capital_gains": row["investment_income"].get("capital_gains", 0.0),
        "tax_federal": row["taxes"].get("federal", 0.0),
        "tax_provincial": row["taxes"].get("provincial", 0.0),
        "tax_net": row["taxes"].get("net_tax", 0.0),
        "net_income_before_optional": row["net_income"].get("before_optional", 0.0),
        "net_income_after_optional": row["net_income"].get("after_optional", 0.0),
        "net_income_target": row["net_income"].get("target", None),
        "balance_REER": row.get("balances", {}).get("REER", 0.0),
        "balance_CELI": row.get("balances", {}).get("CELI", 0.0),
        "balance_CRI": row.get("balances", {}).get("CRI", 0.0),
        "balance_FRV": row.get("balances", {}).get("FRV", 0.0),
        "balance_FERR": row.get("balances", {}).get("FERR", 0.0),
        "balance_Taxable": row.get("balances", {}).get("Taxable", 0.0),
    }
    return flat

def export_csv(results: List[Dict], path: str):
    rows = [flatten_row(r) for r in results]
    if not rows:
        return
    fieldnames = list(rows[0].keys())  # liste fixe définie par flatten_row
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)