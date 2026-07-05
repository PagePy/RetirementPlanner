# services/splitting.py
def split_pension(pension_amount: float, split_ratio: float) -> tuple:
    """
    Retourne (pour_contribuant, pour_conjoint) après fractionnement.
    split_ratio: 0.0 à 0.5 (max légal 50%).
    """
    r = max(0.0, min(0.5, split_ratio))
    to_spouse = pension_amount * r
    remaining = pension_amount - to_spouse
    return remaining, to_spouse