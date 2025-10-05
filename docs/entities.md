
# Entities Contract (Starter)

This document defines the public behavior of entities exposed by the **Normalize Lights** integration.

## 1. Proxy Light (per fixture)
**Domain:** `light`  
**Color modes:** `{ brightness }` (v1)  
**Supported services/kwargs:**

| Service              | Args                              | Behavior |
|----------------------|-----------------------------------|----------|
| `light.turn_on`      | `brightness` (0–255)              | Sets virtual scalar → transform → applies absolute brightness to target. |
|                      | `brightness_step` (± int)         | Applies relative step in virtual domain; clamps; transforms; applies absolute to target. |
|                      | `brightness_step_pct` (± int %)   | Same as above, percent of 255. |
|                      | `transition` (sec)                | Delegates to target if supported; else emulate basic tween (v1 basic or TODO). |
| `light.turn_off`     | `transition` (sec, optional)      | Delegates if supported; else immediate off. |

**Attributes reported:** `is_on`, `brightness (virtual)`, `supported_color_modes={brightness}`.  
**Availability:** mirrors target availability.  
**Reverse sync:** on target brightness change, recompute virtual and update state (ignore self‑originated updates via context).  
**Edge cases:** if off and step > 0, turns on at computed brightness; step < 0 while off → no‑op (documented).

## 2. Room Light (optional)
**Domain:** `light`  
**Members:** list of Proxy Lights.  
**Aggregation:** v1 default = last‑set; (future: median/min/mean).

| Service              | Args                              | Behavior |
|----------------------|-----------------------------------|----------|
| `light.turn_on`      | `brightness`, `brightness_step(_pct)`, `transition` | Applies to virtual scalar, transforms per member, fans out absolute brightness to each target; passes `transition`. |
| `light.turn_off`     | `transition` (optional)           | Fans out off. |

**Attributes reported:** `is_on` (any member on), `brightness` (last‑set or selected aggregation).  
**Reverse sync:** changes from members may update room state (policy: last‑set wins in v1).  
**Edge cases:** partial availability handled by skipping unavailable members.
