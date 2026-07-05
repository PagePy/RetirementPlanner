# models/cri.py
from .account_base import Account
class CRI(Account):
    locked: bool = True  # No withdrawals before allowed age