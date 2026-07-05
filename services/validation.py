# services/validation.py
def validate_inputs(person, contrib):
    assert 0.0 <= contrib.reer_pct <= 1.0
    assert 0.0 <= contrib.cri_pct <= 1.0
    assert contrib.reer_fixed >= 0.0
    assert contrib.cri_fixed >= 0.0
    assert contrib.celi_fixed >= 0.0
    assert person.salary >= 0.0
    