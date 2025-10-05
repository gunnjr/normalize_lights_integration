from __future__ import annotations
from homeassistant.core import HomeAssistant
from .const import DOMAIN

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    # YAML setup not required initially
    return True

async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    # ConfigEntry setup (to be implemented when config_flow is ready)
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    # Unload logic for ConfigEntry (placeholder)
    return True
