# Third Party Notices

## World Monitor

Parts of the market intelligence map interaction model are adapted from
[koala73/worldmonitor](https://github.com/koala73/worldmonitor), including
the map provider pattern, regional view presets, zoom-threshold idea, localized
label handling, and great-circle path helper.

World Monitor is licensed under AGPL-3.0. The upstream license is available at:
https://github.com/koala73/worldmonitor/blob/main/LICENSE

Local modifications:

- Ported selected map utilities from React/TypeScript to this Vue 3 frontend.
- Kept the current A-share event data model instead of importing World Monitor's
  full data schema.
- Added a Chinese detail basemap fallback for domestic network reliability.
