# custom_components/normalize_lights/engine.py

def clamp_0_255(n: int) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(255, n))

def virtual_to_actual(v: int, llv: int | None = None, hld: int | None = None, profile: str | None = None) -> int:
    # IMT v1: identity clamp
    return clamp_0_255(v)

def actual_to_virtual(a: int, llv: int | None = None, hld: int | None = None, profile: str | None = None) -> int:
    # IMT v1: identity clamp
    return clamp_0_255(a)