# engine/timeline.py
class YearContext:
    def __init__(self, year: int, person, accounts, fiscal, carry):
        self.year = year
        self.person = person
        self.accounts = accounts
        self.fiscal = fiscal
        self.carry = carry
        self.outputs = {}

    def grow_accounts(self):
        for acc in self.accounts.values():
            acc.grow()
            