"""numpy-safe JSON helper (#708): cast numpy scalars/arrays to plain Python.

Non-finite floats (NaN, +/-inf) become None so the output always passes
``json.dumps(..., allow_nan=False)``.
"""
import math
from typing import Any

import numpy as np


def json_safe(obj: Any) -> Any:
    """Cast numpy scalars/arrays to plain Python so json.dumps works."""
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        value = float(obj)
        return value if math.isfinite(value) else None
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, np.ndarray):
        return json_safe(obj.tolist())
    return obj
