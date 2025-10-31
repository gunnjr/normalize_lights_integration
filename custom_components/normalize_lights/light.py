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

# helper to ensure clean read from config file
def _as_int_or_none(v):
    if v is None:
        return None  # nothing was provided in YAML
    try:
        return int(v)  # convert cleanly (handles "20" -> 20)
    except (TypeError, ValueError):
        return None  # if it's not a valid integer, ignore it

class NormalizeProxyLight(LightEntity):
    _attr_has_entity_name = True  # allow HA to derive entity_id from name if no suggestion

    """A virtual light that proxies another light and mirrors its state (IMT)."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_should_poll = False


    def __init__(self, hass, name, target_entity, llv=None, hld=None, profile="linear", unique_id: str | None = None ) -> None:
        self.hass = hass
        self._attr_name = name
        self._target_entity_id = target_entity
        self._attr_is_on = False
        self._virtual_brightness = 0  # proxy's brightness (virtual domain)
        self._unsub_target = None
        # Use provided unique_id (typically domain:entry_id) or fallback to target-based
        self._attr_unique_id = unique_id or f"{DOMAIN}:{self._target_entity_id}"
        self._llv = llv
        self._hld = hld
        self._profile = profile

    # ---- HA properties ----
    @property
    def brightness(self) -> Optional[int]:
        return self._virtual_brightness if self._attr_is_on else None

    @property
    def device_info(self):
        """Show this proxy as its own device with the proxy's name."""
        return {
            "identifiers": {("normalize_lights", self._attr_unique_id)},
            "name": self._attr_name,
            "manufacturer": "Community",
            "model": "NormalizeProxyLight",
        }
    # ---- Lifecycle ----
    async def async_added_to_hass(self) -> None:
        """Subscribe to target changes and prime local state."""
        _LOGGER.debug("normalize_lights: async_added_to_hass for %s (target=%s)", self.name, self._target_entity_id)

        # Prime from current target state
        st = self.hass.states.get(self._target_entity_id)
        if st:
            _LOGGER.debug("normalize_lights: priming from target state: %s", st)
            self._apply_target_state(st)
        else:
            _LOGGER.debug("normalize_lights: target state not found at add (%s)", self._target_entity_id)

        # Listen for future target state changes
        self._unsub_target = async_track_state_change_event(
            self.hass, [self._target_entity_id], self._handle_target_event
        )
        _LOGGER.debug("normalize_lights: subscribed to target events for %s", self._target_entity_id)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_target:
            self._unsub_target()
            self._unsub_target = None
            _LOGGER.debug("normalize_lights: unsubscribed from target events for %s", self._target_entity_id)

    # ---- Proxy behavior (proxy -> target) ----
    async def async_turn_on(self, **kwargs) -> None:
        """Accept virtual brightness (absolute/relative), transform, and call the real light."""
        v = self._virtual_brightness

        # Absolute first
        if ATTR_BRIGHTNESS in kwargs:
            v = _clamp(kwargs.get(ATTR_BRIGHTNESS))

        # Relative steps (step wins over pct if both supplied)
        if ATTR_BRIGHTNESS_STEP in kwargs:
            v = _clamp(v + int(kwargs[ATTR_BRIGHTNESS_STEP]))
        elif ATTR_BRIGHTNESS_STEP_PCT in kwargs:
            step = int(255 * (int(kwargs[ATTR_BRIGHTNESS_STEP_PCT]) / 100))
            v = _clamp(v + step)

        # IMT identity transform
        a = virtual_to_actual(v, self._llv, self._hld, self._profile)
        if a == 0:
            a = 1  # ensure we turn the light on

        # Some targets don't support brightness; detect and tailor payload
        target_state = self.hass.states.get(self._target_entity_id)
        supports_brightness = True
        if target_state:
            # Prefer supported_color_modes check when available
            scms = target_state.attributes.get("supported_color_modes")
            if isinstance(scms, (set, list)):
                supports_brightness = ("brightness" in scms) or (ColorMode.BRIGHTNESS in scms)
        service_data = {"entity_id": self._target_entity_id}
        if supports_brightness:
            service_data[ATTR_BRIGHTNESS] = a

        if ATTR_TRANSITION in kwargs:
            service_data[ATTR_TRANSITION] = kwargs[ATTR_TRANSITION]

        _LOGGER.debug("normalize_lights → light.turn_on %s", service_data)
        await self.hass.services.async_call("light", "turn_on", service_data, blocking=True)

        # Optimistic local update; mirror will confirm/correct shortly
        self._virtual_brightness = v
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        service_data = {"entity_id": self._target_entity_id}
        if ATTR_TRANSITION in kwargs:
            service_data[ATTR_TRANSITION] = kwargs[ATTR_TRANSITION]

        _LOGGER.debug("normalize_lights → light.turn_off %s", service_data)
        await self.hass.services.async_call("light", "turn_off", service_data, blocking=True)

        self._attr_is_on = False
        self._virtual_brightness = 0
        self.async_write_ha_state()

    # ---- Mirror (target -> proxy) ----
    async def _handle_target_event(self, event) -> None:
        new_state: Optional[State] = event.data.get("new_state")
        if new_state:
            _LOGGER.debug("normalize_lights: target state changed: %s", new_state)
            self._apply_target_state(new_state)
            self.async_write_ha_state()

    def _apply_target_state(self, state: State) -> None:
        is_on = (state.state or "").lower() == "on"
        self._attr_is_on = is_on

        a = state.attributes.get(ATTR_BRIGHTNESS)
        if a is None:
            # Device doesn't expose brightness; mirror on/off only
            self._virtual_brightness = 255 if is_on else 0
            return

        v = actual_to_virtual(a, self._llv, self._hld, self._profile)
        self._virtual_brightness = v


# ---- YAML Setup Hooks (platform mode for IMT) ----
def setup_platform(hass, config, add_entities, discovery_info=None):
    """Sync wrapper for legacy YAML setup."""
    _LOGGER.debug("normalize_lights: setup_platform shim called with config=%s", config)
    hass.async_create_task(async_setup_platform(hass, config, add_entities, discovery_info))

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Primary async setup for YAML configuration."""
    name    = config.get("name") or f"Proxy for {config.get('target', 'unknown')}"
    target  = config["target"]
    llv_raw = config.get("llv")
    hld_raw = config.get("hld")
    llv = _as_int_or_none(llv_raw)
    hld = _as_int_or_none(hld_raw)
    profile = str(config.get("profile", "linear"))

    _LOGGER.debug(
        "normalize_lights: async_setup_platform for %s → %s (llv=%s, hld=%s, profile=%s)",
        name, target, llv, hld, profile
    )

    async_add_entities(
        [NormalizeProxyLight(hass, name, target, llv, hld, profile)],
        update_before_add=False
    )
 
# Platform-level setup function.
# Home Assistant calls this automatically when a ConfigEntry for this integration is added or reloaded.
# It should instantiate and register NormalizeProxyLight entities based on entry data.    
async def async_setup_entry(hass, entry, async_add_entities):
    from homeassistant.helpers import entity_registry as er
    
    data = {**entry.data, **entry.options}
    name = data["name"]
    target = data["target"]
    llv = int(data.get("llv", 0))
    hld = int(data.get("hld", 255))
    profile = data.get("profile", "linear")
    suggested = data.get("proxy_object_id")  # may be None/empty

    _LOGGER.debug("normalize_lights: async_setup_entry - name=%s, target=%s, suggested=%s", name, target, suggested)

    # Use domain-prefixed ConfigEntry UUID for stable, unique identification
    unique_id = f"{DOMAIN}:{entry.entry_id}"

    # Check if entity already exists in registry
    registry = er.async_get(hass)
    existing_entity = registry.async_get_entity_id("light", DOMAIN, unique_id)
    
    if existing_entity:
        _LOGGER.debug("normalize_lights: entity already exists with ID: %s", existing_entity)
    elif suggested:
        # Try to register the entity with our preferred entity_id
        desired_entity_id = f"light.{suggested}"
        _LOGGER.debug("normalize_lights: attempting to register entity with desired ID: %s", desired_entity_id)
        
        # Check if the desired entity_id is available
        if not registry.async_get(desired_entity_id):
            try:
                # Pre-register the entity with our desired entity_id
                registry.async_get_or_create(
                    domain="light",
                    platform=DOMAIN,
                    unique_id=unique_id,
                    suggested_object_id=suggested,
                    config_entry=entry,
                )
                _LOGGER.debug("normalize_lights: pre-registered entity with suggested ID: %s", suggested)
            except Exception as e:
                _LOGGER.warning("normalize_lights: failed to pre-register entity: %s", e)
        else:
            _LOGGER.debug("normalize_lights: desired entity_id %s is already taken", desired_entity_id)

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