# services/contributions.py
from dataclasses import dataclass

@dataclass
class ContributionInput:
    reer_pct: float = 0.0       # % of salary
    reer_fixed: float = 0.0     # $
    cri_pct: float = 0.0
    cri_fixed: float = 0.0
    celi_fixed: float = 0.0     # CELI is fixed annually

@dataclass
class CarryForward:
    reer_room: float = 0.0
    celi_room: float = 0.0

def annual_reer_room(salary: float, arc_max: float) -> float:
    return min(arc_max, salary * 0.18)

def apply_contributions(person, accounts, contrib: ContributionInput, carry: CarryForward, fiscal):
    # Compute nominal desired contributions
    desired_reer = person.salary * contrib.reer_pct + contrib.reer_fixed
    desired_cri  = person.salary * contrib.cri_pct  + contrib.cri_fixed
    desired_celi = contrib.celi_fixed

    # Compute available REER room (current year + carry-forward)
    reer_room = annual_reer_room(person.salary, fiscal.REER_MAX) + carry.reer_room

    # Enforce CRI + REER <= REER room
    total_registered = desired_reer + desired_cri
    allowed_registered = min(total_registered, reer_room)

    # Allocate proportionally between REER and CRI
    if total_registered > 0:
        ratio_reer = desired_reer / total_registered
        ratio_cri  = desired_cri  / total_registered
        actual_reer = allowed_registered * ratio_reer
        actual_cri  = allowed_registered * ratio_cri
    else:
        actual_reer = 0.0
        actual_cri  = 0.0

    # Update carry-forward REER
    carry.reer_room = max(0.0, reer_room - allowed_registered)

    # CELI room: current year limit + carry-forward
    celi_room = fiscal.CELI_LIMIT + carry.celi_room
    actual_celi = min(desired_celi, celi_room)
    carry.celi_room = max(0.0, celi_room - actual_celi)

    # Deposit to accounts
    accounts["REER"].deposit(actual_reer)
    accounts["CRI"].deposit(actual_cri)
    accounts["CELI"].deposit(actual_celi)

    return {
        "reer": actual_reer, "cri": actual_cri, "celi": actual_celi,
        "reer_room_remaining": carry.reer_room,
        "celi_room_remaining": carry.celi_room
    }
