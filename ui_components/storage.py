import json, os

CONFIG_DIR = "profiles"

def _ensure_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

def list_profiles():
    _ensure_dir()
    return [f[:-5] for f in os.listdir(CONFIG_DIR) if f.endswith(".json")]

def save_profile(name, data):
    _ensure_dir()
    path = os.path.join(CONFIG_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_profile(name):
    path = os.path.join(CONFIG_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}