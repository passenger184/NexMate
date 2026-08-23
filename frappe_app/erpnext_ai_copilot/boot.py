"""Inject the copilot service address into the Desk boot info.

Set `copilot_api_base` in the site's site_config.json to point at the
FastAPI service; defaults to the local development address.
"""

import frappe


def boot_session(bootinfo) -> None:
    bootinfo.copilot_settings = {
        "api_base": frappe.conf.get("copilot_api_base") or "http://localhost:8000",
    }
