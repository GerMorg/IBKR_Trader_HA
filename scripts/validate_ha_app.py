from __future__ import annotations

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ibkr_trader_ha"

REQUIRED = {
    "config.yaml",
    "Dockerfile",
    "run.sh",
    "README.md",
    "DOCS.md",
    "CHANGELOG.md",
    "apparmor.txt",
    "pyproject.toml",
}
missing = sorted(name for name in REQUIRED if not (APP / name).exists())
if missing:
    raise SystemExit(f"missing Home Assistant app files: {missing}")

cfg = yaml.safe_load((APP / "config.yaml").read_text(encoding="utf-8"))
for key in ("name", "version", "slug", "description", "arch"):
    if key not in cfg:
        raise SystemExit(f"config.yaml missing: {key}")
if cfg["arch"] != ["amd64", "aarch64"]:
    raise SystemExit("arch must be amd64 and aarch64")
if cfg.get("homeassistant_api") is not True:
    raise SystemExit("homeassistant_api must be enabled")
if not isinstance(cfg.get("apparmor", True), bool):
    raise SystemExit("apparmor must be a boolean")
map_types = [
    entry.get("type")
    for entry in cfg.get("map", [])
    if isinstance(entry, dict)
]
if "addon_config" not in map_types:
    raise SystemExit("map must include addon_config")
if "app_config" in map_types:
    raise SystemExit("app_config is obsolete; use addon_config")
if cfg.get("host_network", False):
    raise SystemExit("host_network is not permitted")
if cfg.get("full_access", False):
    raise SystemExit("full_access is not permitted")

docker = (APP / "Dockerfile").read_text(encoding="utf-8")
for marker in ('io.hass.type="app"', "io.hass.version"):
    if marker not in docker:
        raise SystemExit(f"Dockerfile missing HA label: {marker}")

run_lines = (APP / "run.sh").read_text(encoding="utf-8").splitlines()
if not run_lines or not run_lines[0].startswith("#!/usr/bin/with-contenv "):
    raise SystemExit("run.sh must use with-contenv")

profile = (APP / "apparmor.txt").read_text(encoding="utf-8")
for required_rule in ("/init rix", "/etc/s6/**", "/run/{s6,s6-rc*,service}/**"):
    if required_rule not in profile:
        raise SystemExit(f"apparmor.txt missing S6 rule: {required_rule}")

for path in ROOT.rglob("config.yaml"):
    if path != APP / "config.yaml":
        raise SystemExit(f"unexpected nested config.yaml: {path}")

app_module = APP / "app"
if not (app_module / "__init__.py").exists():
    raise SystemExit("app/__init__.py missing")

print("Home Assistant app structure valid")
