
# Normalize Lights – Config Entries Guide

This document describes how the integration enables **UI-based configuration** in Home Assistant using **Config Entries** and how proxy light entities are constructed from entry data. It’s written for contributors working inside `custom_components/normalize_lights`.

> IMT mindset: keep changes **minimal but testable**, then iterate.

---

## Folder & File Layout (recommended)

```
custom_components/normalize_lights/
├── __init__.py                 # integration setup: async_setup_entry / async_unload_entry
├── light.py                    # platform code: entity class + platform async_setup_entry
├── engine.py                   # brightness mapping functions (virtual↔actual)
├── helpers.py                  # small utilities (e.g., unique_id helper)
├── manifest.json               # include "config_flow": true
├── config_flow.py              # (next) UI flow to create proxies
├── options_flow.py             # (later) UI to edit LLV/HLD etc.
└── docs/
    └── CONFIG_ENTRIES.md       # this file
```

---

## Step 1 — Enable Config Entries

### 1.1 Add the flag to `manifest.json`
Add the following key (keeping existing keys intact):
```jsonc
{
  "config_flow": true
}
```
This tells HA the integration **supports UI-based setup**.

### 1.2 Add integration setup handlers in `__init__.py`
Minimal IMT implementation:
```python
# custom_components/normalize_lights/__init__.py
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS: list[str] = ["light"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Normalize Lights from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Normalize Lights config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
```

### 1.3 Platform loader in `light.py` (for entries)
```python
# custom_components/normalize_lights/light.py (excerpt)
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TITLE
from .engine import virtual_to_actual, actual_to_virtual
# from .helpers import ensure_unique_id_for_proxy  # optional helper


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """
    Called by Home Assistant when a ConfigEntry is loaded to set up light entities.
    IMT: build one proxy from entry.data (and entry.options if present).
    """
    data = {**entry.data, **entry.options}  # merge; options override
    name = data["name"]
    target = data["target"]
    llv = int(data.get("llv", 0))
    hld = int(data.get("hld", 255))
    profile = data.get("profile", "linear")

    # unique_id: if you're not using a helper yet, you can derive a temporary fallback
    unique_id = f"{DOMAIN}:{entry.data.get('uuid', target)}"

    ent = NormalizeProxyLight(
        hass=hass,
        name=name,
        target_entity=target,
        llv=llv,
        hld=hld,
        profile=profile,
        unique_id=unique_id,
    )
    async_add_entities([ent], update_before_add=False)
```

> Note: YAML setup (`async_setup_platform`) can coexist for now. Entries and YAML should not define **the same** proxy.

---

## Step 2 — Config Data Model

Keep the stored schema **flat** and stable.

### 2.1 Schema (stored in `entry.data`)
- `name: str` — Friendly display name for the proxy
- `target: str` — Entity ID of the real light (e.g., `light.mba_s1_2`)
- `llv: int` — Low visible level (0–255); we store raw 0–255, even if UI shows %
- `hld: int` — Highest level still visibly dimmed (0–255)
- `profile: str` — Mapping profile, default `"linear"` (room for future curves)
- `uuid: str` — Generated at creation; used to build `unique_id`

**Validation:**
- `0 ≤ llv ≤ hld ≤ 255`
- `profile in {"linear"}` (for now)

### 2.2 Identity & naming
- `unique_id` should be **non-meaningful and stable**: `f"{DOMAIN}:{uuid}"`
- `entity_id` pattern: `<target>_proxy` (e.g., `light.mba_s1_2_proxy`)
- `name` is user-facing and may differ from `entity_id`

### 2.3 Options (later)
Edits made via the Options Flow are stored in `entry.options` using the same keys. Always merge `data | options` at runtime.

---

## Optional Helpers (recommended)

### `helpers.py` — persistent UUID for entries
```python
# custom_components/normalize_lights/helpers.py
from __future__ import annotations

import uuid as _uuid
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN


async def ensure_unique_id_for_proxy(hass: HomeAssistant, entry: Optional[ConfigEntry], target_entity: str) -> str:
    """
    Return a stable, non-meaningful unique_id.
    - ConfigEntry mode: persist a UUID in entry.data['uuid']
    - YAML mode: deterministic fallback derived from target
    """
    if entry is not None:
        uid = entry.data.get("uuid")
        if not uid:
            uid = str(_uuid.uuid4())
            hass.config_entries.async_update_entry(entry, data={**entry.data, "uuid": uid})
        return f"{DOMAIN}:{uid}"
    return f"{DOMAIN}:{target_entity}"
```

### Factory for entities
```python
# custom_components/normalize_lights/light.py (or factory.py)
def create_proxy_entity(hass, conf: dict) -> NormalizeProxyLight:
    return NormalizeProxyLight(
        hass=hass,
        name=conf["name"],
        target_entity=conf["target"],
        llv=int(conf.get("llv", 0)),
        hld=int(conf.get("hld", 255)),
        profile=conf.get("profile", "linear"),
        unique_id=conf.get("unique_id"),
    )
```

---

## Testing & Validation (manual)

1. **Core check & restart**
   - In a terminal on HA:
     ```bash
     ha core check && ha core restart
     ```
2. **UI presence**
   - Go to **Settings → Devices & Services → Integrations**.
   - Confirm “Normalize Lights” appears as an integration (clicking will work once `config_flow.py` is added).
3. **YAML proxy still works (if present)**
   - Ensure that YAML-defined proxies still load and function as before (unless removed).
4. **Logs**
   - Set logging for our domain to DEBUG and verify setup lines:
     ```yaml
     logger:
       default: warning
       logs:
         custom_components.normalize_lights: debug
     ```

---

## Troubleshooting

- **“Platform error: light - cannot import name …”**  
  Check for typos in imports and ensure files are in `custom_components/normalize_lights/`.

- **“Detected blocking call to import_module … inside the event loop”**  
  Usually a transient loader warning; ensure your modules import quickly (no blocking IO at import time).

- **Proxy doesn’t mirror target**  
  Confirm `async_track_state_change_event` is active in `async_added_to_hass`, and that the entity_id is correct.

- **Proxy → Target writes don’t apply**  
  Verify `light.turn_on` calls include the **target’s** entity_id (not the proxy). Check for brightness support in target attributes.

---

## Next Steps

- **Step 3: `config_flow.py` (IMT)**  
  Minimal form to collect `name`, `target`, `llv`, `hld`, `profile`, generate `uuid`, and create the entry.

- **Step 4: `options_flow.py`**  
  Allow editing LLV/HLD/name/profile. Ensure entries reload on save.

- **Room controller (future)**  
  Schema for grouped proxies, aggregation strategy (`average`/`max`), and broadcast mapping.

---

## Notes on YAML Backward Compatibility

- Keep YAML platform (`async_setup_platform`) running for a while.  
- Avoid having the **same** proxy defined in both YAML and UI.  
- Provide migration guidance later (e.g., a simple doc to delete YAML once UI proxy is created).

---

**Authoring tips**  
- Prefer **async** methods and **non-blocking** imports.  
- Keep logs **structured and low-verbosity** at INFO; use DEBUG for dev.  
- Avoid coupling `unique_id` to mutable names—use UUIDs for config entries.
