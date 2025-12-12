
from typing import List, Dict, Any
import json

def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)
