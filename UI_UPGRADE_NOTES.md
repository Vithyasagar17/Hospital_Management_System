# HMS UI Upgrade

The application UI has been refactored into a consistent modern healthcare workspace while preserving the existing Flask routes, forms, Jinja data bindings, and database behavior.

## What changed
- New responsive authenticated app shell with sidebar, top bar, active navigation state, mobile drawer, and shared flash messages.
- New polished login and registration experience.
- Redesigned Admin, Doctor, and Patient dashboards.
- Unified design system for cards, buttons, forms, tables, badges, tabs, alerts, empty states, and profile details.
- Consistent page titles across all authenticated views.
- Redesigned doctor/patient profile detail views.
- Removed duplicate page-level flash rendering now handled centrally in `layout.html`.
- Updated HMS logo and visual identity.
- Preserved all existing Flask endpoint names and form actions.

## Validation performed
- All 29 Jinja templates compile successfully.
- All template `url_for(...)` endpoint references match functions defined by the registered blueprints.
- Python source compiles successfully with `compileall`.
- CSS braces are balanced.

The runtime Flask launch was not executed in the editing environment because Flask packages were unavailable there and package download access was disabled.
