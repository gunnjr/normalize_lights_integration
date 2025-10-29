# /config/custom_components/normalize_lights/engine.py

def _clamp_0_255(x):
    try:
        x = int(round(float(x)))
    except (TypeError, ValueError):
        x = 0
    return max(0, min(255, x))


def _normalize_bounds(llv, hld):
    llv = 0 if llv is None else _clamp_0_255(llv)
    hld = 255 if hld is None else _clamp_0_255(hld)
    if hld <= llv:
        return 0, 255  # fallback span
    return llv, hld


def virtual_to_actual(v, llv=None, hld=None, profile=None):
    """
    Piecewise mapping:
      v == 0   -> 0 (true off)
      v == 255 -> 255 (true max)
      else     -> scale v∈[1..254] into [LLV..HLD]
    """
    v = _clamp_0_255(v)
    if v == 0:
        return 0
    if v == 255:
        return 255
    lo, hi = _normalize_bounds(llv, hld)
    a = lo + round(((v - 1) / 253) * (hi - lo))
    return _clamp_0_255(a)


def actual_to_virtual(a, llv=None, hld=None, profile=None):
    """
    Inverse mapping:
      a == 0   -> 0
      a >= 255 -> 255
      else     -> scale a∈[LLV..HLD] back to [1..254] (clamped)
    """
    a = _clamp_0_255(a)
    if a == 0:
        return 0
    if a >= 255:
        return 255
    lo, hi = _normalize_bounds(llv, hld)
    span = hi - lo
    if span <= 0:
        return a  # degenerate: identity interior
    a_clamped = max(lo, min(hi, a))
    v = 1 + round(253 * (a_clamped - lo) / span)
    return _clamp_0_255(v)