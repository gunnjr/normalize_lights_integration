# custom_components/normalize_lights/light.py

# If you keep this, it must be first; on Py3.13 it's not required.
# from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_STEP,
    ATTR_BRIGHTNESS_STEP_PCT,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, TITLE
from .engine import virtual_to_actual, actual_to_virtual

_LOGGER = logging.getLogger(__name__)


def _clamp(n: Optional[int]) -> int:
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(255, n))


class NormalizeProxyLight(LightEntity):
    """A minimal virtual light that proxies another light and mirrors its state."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, name: str, target_entity: str) -> None:
        self.hass = hass
        self._attr_name = name
        self._target_entity_id = target_entity
        self._attr_is_on = False
        self._virtual_brightness = 0  # proxy’s brightness in virtual domain
        self._unsub_target = None

    # ---- HA properties ----
    @property
    def brightness(self) -> Optional[int]:
        return self._virtual_brightness if self._attr_is_on else None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"proxy_{self._target_entity_id}")},
            name=f"{TITLE} Proxy",
            manufacturer="Community",
            model="NormalizeProxyLight",
        )

    # ---- Lifecycle ----
    async def async_added_to_hass(self) -> None:
        """Subscribe to target light changes and initialize from current state."""
        # 1) Prime from current target state (if it exists)
        st = self.hass.states.get(self._target_entity_id)
        if st:
            self._apply_target_state(st)

        # 2) Listen for future changes
        self._unsub_target = async_track_state_change_event(
            self.hass, [self._target_entity_id], self._handle_target_event
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_target:
            self._unsub_target()
            self._unsub_target = None

    # ---- Proxy behavior ----
    async def async_turn_on(self, **kwargs) -> None:
        """Consume absolute/relative brightness in the *virtual* domain, transform, and call the real light."""
        # Base on current virtual brightness
        v = self._virtual_brightness

        # Absolute
        if ATTR_BRIGHTNESS in kwargs:
            v = _clamp(kwargs.get(ATTR_BRIGHTNESS))

        # Relative (step takes precedence over pct if both set)
        if ATTR_BRIGHTNESS_STEP in kwargs:
            v = _clamp(v + int(kwargs[ATTR_BRIGHTNESS_STEP]))
        elif ATTR_BRIGHTNESS_STEP_PCT in kwargs:
            step = int(255 * (int(kwargs[ATTR_BRIGHTNESS_STEP_PCT]) / 100))
            v = _clamp(v + step)

        # Identity transform for now: virtual -> actual
        a = virtual_to_actual(v)

        data = {"entity_id": self._target_entity_id}
        # If turning on without brightness argument and current v==0, choose a small nonzero default
        if a == 0:
            a = 1  # minimal "on" brightness
        data[ATTR_BRIGHTNESS] = a

        if ATTR_TRANSITION in kwargs:
            data[ATTR_TRANSITION] = kwargs[ATTR_TRANSITION]

        # Call the real light
        await self.hass.services.async_call("light", "turn_on", data, blocking=False)

        # Optimistic local state (will be corrected by mirror callback if needed)
        self._virtual_brightness = v
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        data = {"entity_id": self._target_entity_id}
        if ATTR_TRANSITION in kwargs:
            data[ATTR_TRANSITION] = kwargs[ATTR_TRANSITION]

        await self.hass.services.async_call("light", "turn_off", data, blocking=False)

        # Optimistic local state
        self._attr_is_on = False
        self._virtual_brightness = 0
        self.async_write_ha_state()

    # ---- Mirror target -> proxy ----
    async def _handle_target_event(self, event) -> None:
        """State change event handler for the target light."""
        new_state: Optional[State] = event.data.get("new_state")
        if new_state:
            self._apply_target_state(new_state)
            self.async_write_ha_state()

    def _apply_target_state(self, state: State) -> None:
        """Map target (actual) -> proxy (virtual), identity for now."""
        is_on = (state.state or "").lower() == "on"
        self._attr_is_on = is_on

        a = state.attributes.get(ATTR_BRIGHTNESS)
        if a is None:
            # If the device doesn't report brightness, just mirror on/off
            self._virtual_brightness = 255 if is_on else 0
            return

        # Identity transform for now: actual -> virtual
        v = actual_to_virtual(a)
        self._virtual_brightness = v


# -------------------------------------------------------------------
# YAML Setup Hooks (platform mode for IMT)
# -------------------------------------------------------------------
def setup_platform(hass, config, add_entities, discovery_info=None):
    """Sync wrapper for legacy YAML setup."""
    hass.async_create_task(async_setup_platform(hass, config, add_entities, discovery_info))


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Primary async setup for YAML configuration."""
    name = config.get("name") or f"Proxy for {config.get('target', 'unknown')}"
    target = config["target"]
    async_add_entities([NormalizeProxyLight(hass, name, target)], update_before_add=False)
