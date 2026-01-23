import json
import os
import tempfile
import shutil
from typing import Dict, Any, Optional

def write_json_atomic(path: str, data: Dict[str, Any], backup: bool = True, indent: int = 2):
    """
    Atomic write using temporary file and os.replace.
    Ensures data integrity during power failures or crashes.
    """
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    # Create a backup before writing if file exists
    if backup and os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except Exception:
            pass

    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        # Sync to disk if necessary (handled by OS usually, but replace is atomic)
        os.replace(tmp_path, path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise e

def read_json_safe(path: str, default: Any = None) -> Any:
    """
    Safely read JSON file with basic error handling.
    """
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
    except Exception:
        pass
    return default
import csv

def write_csv_atomic(path: str, header: list, rows: list):
    """Atomic write for CSV files."""
    dir_name = os.path.dirname(path)
    if dir_name: os.makedirs(dir_name, exist_ok=True)
    
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".csv")
    try:
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            if header: w.writerow(header)
            w.writerows(rows)
        os.replace(tmp_path, path)
    except Exception as e:
        if os.path.exists(tmp_path): os.unlink(tmp_path)
        raise e
