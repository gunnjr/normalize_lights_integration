# /config/custom_components/normalize_lights/config_flow.py
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import DOMAIN

PROFILE_OPTIONS = ["linear"]  # reserved for future curves


def _parse_level(value: Any) -> int | None:
    """
    Accepts:
      - "35%" or " 35 % "  -> percent
      - 35 (int/float)     -> percent (0–100)
      - 204 (int/float)    -> raw 0–255 (if >100)
      - "204" (string)     -> raw 0–255
    Returns int in [0..255] or None if invalid.
    """
    def clamp255(n: float | int) -> int:
        try:
            n = float(n)
        except (TypeError, ValueError):
            return None  # type: ignore[return-value]
        n = max(0.0, min(255.0, n))
        return int(round(n))

    if value is None:
        return None

    # Strings: handle "35%" or "204"
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("%"):
            try:
                pct = float(s[:-1].strip())
            except ValueError:
                return None
            if pct < 0 or pct > 100:
                return None
            return clamp255(255.0 * (pct / 100.0))
        # Plain string number
        try:
            v = float(s)
        except ValueError:
            return None
        # Heuristic: <=100 ⇒ percent; >100 ⇒ raw 0–255
        if 0.0 <= v <= 100.0:
            return clamp255(255.0 * (v / 100.0))
        return clamp255(v)

    # Numbers
    if isinstance(value, (int, float)):
        v = float(value)
        if 0.0 <= v <= 100.0:
            return clamp255(255.0 * (v / 100.0))
        return clamp255(v)

    return None


def _schema():
    # Make llv/hld strings to allow "35%" input
    return vol.Schema(
        {
            vol.Required("name"): str,
            vol.Required("target"): str,  # entity_id, e.g., light.mba_s1_2
            vol.Required("llv", default="0"): str,
            vol.Required("hld", default="255"): str,
            vol.Required("profile", default="linear"): vol.In(PROFILE_OPTIONS),
        }
    )


class NormalizeLightsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input["name"].strip()
            target = user_input["target"].strip()
            profile = user_input["profile"]

            llv_raw = user_input["llv"]
            hld_raw = user_input["hld"]

            llv = _parse_level(llv_raw)
            hld = _parse_level(hld_raw)

            if llv is None or hld is None:
                errors["base"] = "bad_level"
            elif llv > hld:
                errors["base"] = "llv_gt_hld"
            elif await self._target_already_proxied(self.hass, target):
                errors["base"] = "target_in_use"

            if not errors:
                data = {
                    "name": name,
                    "target": target,
                    "llv": llv,   # stored as 0–255
                    "hld": hld,   # stored as 0–255
                    "profile": profile,
                }
                return self.async_create_entry(title=name, data=data)

        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    async def _target_already_proxied(self, hass: HomeAssistant, target: str) -> bool:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.data.get("target") == target:
                return True
        return False