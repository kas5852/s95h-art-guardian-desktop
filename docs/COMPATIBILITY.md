# Compatibility and observed behavior

Tested on one **Samsung QN65S95HAFXZA**, US region, 65-inch S95H, firmware
`T-RSMHAKUC-0100-1235.0`. Results from one unit do not establish support for other
sizes, regions, firmware, or models. The timer setter and scheduled controller
restrict operations to this model code and bind saved state to its device
identity.

## Verified observations

- The Art API responded even though device metadata reported
  `FrameTVSupport: false`.
- Advertised artwork-timer values were 60, 120, 180, and 240 minutes.
- Setting the timer to `off` was acknowledged; a separate settings read returned
  `off`.
- A sampled overnight observation returned Art Mode on and timer off at every
  checkpoint. Periodic reads may affect undocumented inactivity behavior, so
  this is not an input-free continuous-display test.
- The setting survived an owner-reported restart, but later reads found 240
  again. The reset trigger remains unknown.
- Explicit IP Control `powerOff` and `powerOn`, and subsequent Art activation,
  received successful responses and were physically confirmed during a
  supervised test.
- A single Wake-on-LAN attempt failed after a twenty-minute standby interval.
  Explicit IP power-on succeeded. The controller therefore uses IP power-on
  first and one Wake-on-LAN fallback.
- A read after that wake found the timer at 240 again. Reapplying `off` and an
  independent read confirmed the repair.

## Important limits

An API response or sampled checkpoint cannot prove uninterrupted artwork
display, long-term panel safety, or maintenance completion. The standby window
does not replace Samsung's maintenance algorithm. The supervised wake test does
not establish reliability across every long standby period or firmware update.

Pairing behavior can differ between the Art channel and IP Control. Do not assume
that a successful connection to one authorizes the other. Developer Mode is not
required for this desktop utility.

No service-menu settings, manual Pixel Refresh scheduling, firmware patches,
root access, or TV-side sideloaded application are part of this repository.

Protocol reference: [upstream Art implementation](https://github.com/NickWaterton/samsung-tv-ws-api/blob/fe95ef1d784cd32f49bf9a07ec479576574eea07/samsungtvws/art.py).
Maintenance guidance: [Samsung Screen Optimization](https://www.samsung.com/hk_en/support/tv-audio-video/how-to-use-screen-optimization-on-a-samsung-oled-tv/).
