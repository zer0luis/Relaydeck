#!/usr/bin/env python3
"""RelayDeck: install and manage mainstream remote-access tools locally."""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import textwrap
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from getpass import getuser
from pathlib import Path
from typing import Iterable


APP_NAME = "RelayDeck"
APP_TAGLINE = "Local Remote Access Installer & Manager"
SUPPORTED_OS = {"Darwin": "macos", "Windows": "windows"}
DEFAULT_LOG_FILE = str(Path(__file__).with_suffix(".log"))
SETTINGS_URIS = {
    "macos_sharing": "x-apple.systempreferences:com.apple.Sharing-Settings.extension",
    "windows_rdp": "ms-settings:remotedesktop",
}
LOGGER = logging.getLogger(APP_NAME.lower())
ACTIVE_LOG_FILE = DEFAULT_LOG_FILE


class Style:
    """Small ANSI helper for a cleaner interactive menu."""

    enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    reset = "\033[0m" if enabled else ""
    bold = "\033[1m" if enabled else ""
    dim = "\033[2m" if enabled else ""
    cyan = "\033[36m" if enabled else ""
    green = "\033[32m" if enabled else ""
    yellow = "\033[33m" if enabled else ""
    red = "\033[31m" if enabled else ""


@dataclass(frozen=True)
class ToolSpec:
    key: str
    name: str
    description: str
    category: str
    supported_on: tuple[str, ...]
    official_urls: dict[str, str]
    install_kind: str = "vendor_download"
    mac_paths: tuple[str, ...] = ()
    windows_paths: tuple[str, ...] = ()
    windows_registry_names: tuple[str, ...] = ()
    installer_patterns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    settings_uri: str | None = None
    notes: tuple[str, ...] = ()


@dataclass
class ToolStatus:
    installed: bool
    status_label: str
    version: str | None = None
    details: list[str] = field(default_factory=list)
    launch_targets: list[str] = field(default_factory=list)
    installer_candidate: str | None = None


@dataclass
class ValidationCheck:
    name: str
    status: str
    details: str


def build_catalog() -> list[ToolSpec]:
    return [
        ToolSpec(
            key="teamviewer",
            name="TeamViewer",
            description="Attended and unattended remote support with a mainstream cross-platform client.",
            category="Third-party",
            supported_on=("macos", "windows"),
            official_urls={
                "macos": "https://www.teamviewer.com/en/download/portal/macos/",
                "windows": "https://www.teamviewer.com/en-us/download/portal/windows/",
            },
            mac_paths=(
                "/Applications/TeamViewer.app",
                "~/Applications/TeamViewer.app",
            ),
            windows_paths=(
                r"%ProgramFiles%\TeamViewer\TeamViewer.exe",
                r"%ProgramFiles(x86)%\TeamViewer\TeamViewer.exe",
            ),
            windows_registry_names=("TeamViewer",),
            installer_patterns={
                "macos": (r"teamviewer.*\.(dmg|pkg)$",),
                "windows": (r"teamviewer.*\.(exe|msi)$",),
            },
            notes=(
                "Prefer attended sessions unless you explicitly need unattended access.",
                "Review host access settings before sharing persistent IDs or passwords.",
            ),
        ),
        ToolSpec(
            key="anydesk",
            name="AnyDesk",
            description="Lightweight remote desktop for quick support sessions and device access.",
            category="Third-party",
            supported_on=("macos", "windows"),
            official_urls={
                "macos": "https://anydesk.com/en/downloads/mac-os",
                "windows": "https://anydesk.com/en/downloads/windows",
            },
            mac_paths=(
                "/Applications/AnyDesk.app",
                "~/Applications/AnyDesk.app",
            ),
            windows_paths=(
                r"%ProgramFiles%\AnyDesk\AnyDesk.exe",
                r"%ProgramFiles(x86)%\AnyDesk\AnyDesk.exe",
                r"%LocalAppData%\AnyDesk\AnyDesk.exe",
            ),
            windows_registry_names=("AnyDesk",),
            installer_patterns={
                "macos": (r"anydesk.*\.(dmg|pkg)$",),
                "windows": (r"anydesk.*\.(exe|msi)$",),
            },
            notes=(
                "Validate the remote address before approving an incoming or outgoing session.",
                "Set unattended access only on machines you administer directly.",
            ),
        ),
        ToolSpec(
            key="realvnc",
            name="RealVNC Connect",
            description="Commercial VNC suite with separate viewer and server components.",
            category="Third-party",
            supported_on=("macos", "windows"),
            official_urls={
                "macos": "https://www.realvnc.com/en/connect/download/vnc/",
                "windows": "https://www.realvnc.com/en/connect/download/vnc/",
            },
            mac_paths=(
                "/Applications/VNC Viewer.app",
                "/Applications/VNC Server.app",
                "/Applications/RealVNC/VNC Viewer.app",
                "/Applications/RealVNC/VNC Server.app",
                "~/Applications/VNC Viewer.app",
                "~/Applications/VNC Server.app",
            ),
            windows_paths=(
                r"%ProgramFiles%\RealVNC\VNC Viewer\vncviewer.exe",
                r"%ProgramFiles%\RealVNC\VNC Server\vncserver.exe",
                r"%ProgramFiles(x86)%\RealVNC\VNC Viewer\vncviewer.exe",
                r"%ProgramFiles(x86)%\RealVNC\VNC Server\vncserver.exe",
            ),
            windows_registry_names=("RealVNC", "VNC Viewer", "VNC Server"),
            installer_patterns={
                "macos": (r"(vnc|realvnc).*\.(dmg|pkg)$",),
                "windows": (r"(vnc|realvnc).*\.(exe|msi)$",),
            },
            notes=(
                "Viewer and server ship separately; status output will tell you which side is present.",
                "Use strong authentication if you expose a VNC server beyond a local network.",
            ),
        ),
        ToolSpec(
            key="screen-sharing",
            name="macOS Screen Sharing",
            description="Built-in macOS screen sharing and management settings.",
            category="Built-in",
            supported_on=("macos",),
            official_urls={
                "macos": "https://support.apple.com/guide/mac-help/mh11848/mac",
            },
            install_kind="system_feature",
            mac_paths=(
                "/System/Library/CoreServices/Applications/Screen Sharing.app",
            ),
            settings_uri=SETTINGS_URIS["macos_sharing"],
            notes=(
                "This is a system feature, so the script opens the right settings page instead of downloading anything.",
                "For full remote management, verify the permissions granted in macOS Sharing settings.",
            ),
        ),
        ToolSpec(
            key="windows-rdp",
            name="Windows Remote Desktop",
            description="Built-in Windows remote desktop host settings and launch helpers.",
            category="Built-in",
            supported_on=("windows",),
            official_urls={
                "windows": "https://support.microsoft.com/en-us/windows/how-to-use-remote-desktop-5fe128d5-8fb1-7a23-3b8a-41e636865e8c",
            },
            install_kind="system_feature",
            settings_uri=SETTINGS_URIS["windows_rdp"],
            notes=(
                "This is a system feature, so the script opens Remote Desktop settings rather than fetching an installer.",
                "Remote Desktop host support depends on the Windows edition installed on the machine.",
            ),
        ),
    ]


def configure_logging(log_file: str, verbose: bool = False) -> None:
    global ACTIVE_LOG_FILE
    path = Path(log_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_LOG_FILE = str(path)

    LOGGER.handlers.clear()
    LOGGER.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOGGER.propagate = False

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)

    if verbose:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        LOGGER.addHandler(stream_handler)


def log_event(event: str, **fields: object) -> None:
    payload = {"event": event, **fields}
    LOGGER.info(json.dumps(payload, sort_keys=True, default=str))


def detect_os_family() -> str:
    raw = platform.system()
    if raw not in SUPPORTED_OS:
        supported = ", ".join(sorted(SUPPORTED_OS.values()))
        raise SystemExit(f"{APP_NAME} supports {supported}. Detected: {raw}")
    return SUPPORTED_OS[raw]


def expand_path(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


def run_command(args: list[str], timeout: int = 8) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_report_path() -> str:
    safe_host = re.sub(r"[^A-Za-z0-9_.-]+", "-", socket.gethostname()).strip("-") or "host"
    filename = f"relaydeck-report-{safe_host}-{timestamp_slug()}.json"
    return str(Path(__file__).resolve().parent / filename)


def host_metadata(os_family: str) -> dict[str, str]:
    metadata = {
        "app_name": APP_NAME,
        "app_tagline": APP_TAGLINE,
        "hostname": socket.gethostname(),
        "user": getuser(),
        "os_family": os_family,
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "python_version": platform.python_version(),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if os_family == "macos":
        metadata["os_version"] = platform.mac_ver()[0] or "unknown"
    else:
        metadata["os_version"] = platform.release() or "unknown"
    return metadata


def read_macos_app_version(app_path: str) -> str | None:
    plist_path = Path(app_path) / "Contents" / "Info.plist"
    if not plist_path.exists():
        return None
    try:
        with plist_path.open("rb") as handle:
            info = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    return info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")


def find_recent_installer(tool: ToolSpec, os_family: str) -> str | None:
    patterns = tool.installer_patterns.get(os_family, ())
    if not patterns:
        return None

    downloads_dir = Path.home() / "Downloads"
    if not downloads_dir.exists():
        return None

    candidates: list[Path] = []
    for entry in downloads_dir.iterdir():
        if not entry.is_file():
            continue
        for pattern in patterns:
            if re.search(pattern, entry.name, flags=re.IGNORECASE):
                candidates.append(entry)
                break

    if not candidates:
        return None

    newest = max(candidates, key=lambda item: item.stat().st_mtime)
    return str(newest)


def first_non_empty(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def detect_macos_vendor_status(tool: ToolSpec) -> ToolStatus:
    installed_paths = [expand_path(path) for path in tool.mac_paths if Path(expand_path(path)).exists()]
    version = None
    if installed_paths:
        version = first_non_empty(read_macos_app_version(path) for path in installed_paths)

    status = ToolStatus(
        installed=bool(installed_paths),
        status_label="Installed" if installed_paths else "Not installed",
        version=version,
        launch_targets=installed_paths,
        installer_candidate=find_recent_installer(tool, "macos"),
    )

    if installed_paths:
        status.details.append(f"Bundle found at {installed_paths[0]}")
    else:
        status.details.append("No app bundle found in standard macOS application folders.")
    if version:
        status.details.append(f"Version: {version}")
    return status


def get_windows_uninstall_entries() -> list[dict[str, str]]:
    try:
        import winreg
    except ImportError:
        return []

    entries: list[dict[str, str]] = []
    registry_roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )

    for root, subkey in registry_roots:
        try:
            with winreg.OpenKey(root, subkey) as handle:
                key_count = winreg.QueryInfoKey(handle)[0]
                for index in range(key_count):
                    entry_name = winreg.EnumKey(handle, index)
                    try:
                        with winreg.OpenKey(handle, entry_name) as item:
                            display_name = _read_reg_value(item, "DisplayName")
                            if not display_name:
                                continue
                            entries.append(
                                {
                                    "display_name": display_name,
                                    "display_version": _read_reg_value(item, "DisplayVersion") or "",
                                    "install_location": _read_reg_value(item, "InstallLocation") or "",
                                }
                            )
                    except OSError:
                        continue
        except OSError:
            continue
    return entries


def _read_reg_value(handle, value_name: str) -> str | None:
    try:
        import winreg
    except ImportError:
        return None
    try:
        value, _ = winreg.QueryValueEx(handle, value_name)
    except OSError:
        return None
    return str(value).strip() if value else None


def detect_windows_vendor_status(tool: ToolSpec) -> ToolStatus:
    installed_paths = [expand_path(path) for path in tool.windows_paths if Path(expand_path(path)).exists()]
    registry_entries = get_windows_uninstall_entries()
    matching_entries = []
    for entry in registry_entries:
        display_name = entry["display_name"].casefold()
        if any(name.casefold() in display_name for name in tool.windows_registry_names):
            matching_entries.append(entry)

    version = first_non_empty(entry.get("display_version") for entry in matching_entries)
    status = ToolStatus(
        installed=bool(installed_paths or matching_entries),
        status_label="Installed" if (installed_paths or matching_entries) else "Not installed",
        version=version,
        launch_targets=installed_paths.copy(),
        installer_candidate=find_recent_installer(tool, "windows"),
    )

    if installed_paths:
        status.details.append(f"Executable found at {installed_paths[0]}")
    elif matching_entries:
        status.details.append(f"Matched installed app entry: {matching_entries[0]['display_name']}")
        install_location = matching_entries[0].get("install_location")
        if install_location:
            status.details.append(f"Install location: {install_location}")
    else:
        status.details.append("No executable or uninstall entry found in standard Windows locations.")
    if version:
        status.details.append(f"Version: {version}")
    return status


def detect_macos_screen_sharing_status(tool: ToolSpec) -> ToolStatus:
    launchctl_code, launchctl_out, _ = run_command(["launchctl", "print-disabled", "system"])
    enabled = False
    if launchctl_code == 0:
        enabled = '"com.apple.screensharing" => enabled' in launchctl_out

    app_path = first_non_empty(expand_path(path) for path in tool.mac_paths if Path(expand_path(path)).exists())
    status = ToolStatus(
        installed=bool(app_path),
        status_label="Enabled" if enabled else "Disabled",
        version=read_macos_app_version(app_path) if app_path else None,
        launch_targets=[app_path] if app_path else [],
    )
    if app_path:
        status.details.append(f"Client app available at {app_path}")
    if launchctl_code == 0:
        status.details.append("Sharing service state read from launchctl.")
    else:
        status.details.append("Could not read launchctl state; open Sharing settings to verify.")
    if not enabled:
        status.details.append("Open Sharing settings to enable or review access permissions.")
    return status


def detect_windows_rdp_status() -> ToolStatus:
    try:
        import winreg
    except ImportError:
        return ToolStatus(installed=False, status_label="Unavailable", details=["Windows registry APIs are unavailable."])

    enabled = None
    edition = None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Terminal Server") as handle:
            value, _ = winreg.QueryValueEx(handle, "fDenyTSConnections")
            enabled = value == 0
    except OSError:
        pass

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as handle:
            edition = _read_reg_value(handle, "ProductName")
    except OSError:
        pass

    code, stdout, _ = run_command(["sc", "query", "TermService"])
    service_line = next((line.strip() for line in stdout.splitlines() if "STATE" in line), None) if code == 0 else None

    status = ToolStatus(
        installed=True,
        status_label="Enabled" if enabled else "Disabled" if enabled is not None else "Unknown",
    )
    if edition:
        status.details.append(f"Edition: {edition}")
        if "home" in edition.casefold():
            status.details.append("Windows Home does not expose the full Remote Desktop host feature.")
    if service_line:
        status.details.append(service_line)
    if enabled is None:
        status.details.append("Open Remote Desktop settings to confirm host status.")
    return status


def detect_status(tool: ToolSpec, os_family: str) -> ToolStatus:
    if tool.key == "screen-sharing" and os_family == "macos":
        return detect_macos_screen_sharing_status(tool)
    if tool.key == "windows-rdp" and os_family == "windows":
        return detect_windows_rdp_status()
    if os_family == "macos":
        return detect_macos_vendor_status(tool)
    return detect_windows_vendor_status(tool)


def make_check(name: str, condition: bool, ok_details: str, fail_details: str) -> ValidationCheck:
    return ValidationCheck(name=name, status="pass" if condition else "fail", details=ok_details if condition else fail_details)


def validate_command(name: str, command: list[str], ok_details: str, fail_prefix: str) -> ValidationCheck:
    code, stdout, stderr = run_command(command)
    if code == 0:
        detail = ok_details
        if stdout:
            first_line = stdout.splitlines()[0]
            detail = f"{ok_details} ({first_line})"
        return ValidationCheck(name=name, status="pass", details=detail)
    detail = stderr or stdout or "command failed"
    return ValidationCheck(name=name, status="fail", details=f"{fail_prefix}: {detail}")


def validate_tool(tool: ToolSpec, os_family: str, status: ToolStatus | None = None) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    current_status = status or detect_status(tool, os_family)
    source_url = tool.official_urls.get(os_family)

    checks.append(
        make_check(
            "official_source",
            bool(source_url),
            f"Official source configured: {source_url}",
            "Official source missing for this OS.",
        )
    )

    if tool.install_kind == "vendor_download":
        installer_patterns = tool.installer_patterns.get(os_family, ())
        checks.append(
            make_check(
                "installer_pattern",
                bool(installer_patterns),
                f"Installer filename pattern configured for {os_family}.",
                f"No installer filename pattern configured for {os_family}.",
            )
        )

    if os_family == "macos":
        checks.extend(validate_tool_macos(tool, current_status))
    elif os_family == "windows":
        checks.extend(validate_tool_windows(tool, current_status))

    return checks


def validate_tool_macos(tool: ToolSpec, status: ToolStatus) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    expected_paths = [expand_path(path) for path in tool.mac_paths]
    checks.append(
        make_check(
            "mac_paths_configured",
            bool(expected_paths),
            f"{len(expected_paths)} macOS path candidates configured.",
            "No macOS path candidates configured.",
        )
    )
    checks.append(
        make_check(
            "detector_execution",
            True,
            f"Status probe completed with label '{status.status_label}'.",
            "Status probe failed.",
        )
    )

    if tool.key == "screen-sharing":
        checks.append(
            make_check(
                "settings_uri",
                bool(tool.settings_uri),
                f"Settings URI configured: {tool.settings_uri}",
                "Settings URI missing for macOS Screen Sharing.",
            )
        )
        checks.append(
            validate_command(
                "launchctl_probe",
                ["launchctl", "print-disabled", "system"],
                "launchctl responded for screen sharing service state.",
                "launchctl probe failed",
            )
        )
    else:
        expected_text = f"Installed bundle detected at {status.launch_targets[0]}" if status.launch_targets else "Tool is not installed on this host, but detection paths were checked."
        checks.append(
            ValidationCheck(
                name="installation_probe",
                status="pass",
                details=expected_text,
            )
        )
    return checks


def validate_windows_runtime() -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    try:
        import winreg

        checks.append(ValidationCheck(name="winreg_import", status="pass", details=f"winreg available from {winreg.__name__}."))
    except ImportError:
        checks.append(ValidationCheck(name="winreg_import", status="fail", details="winreg import failed."))
        return checks

    try:
        entries = get_windows_uninstall_entries()
        checks.append(ValidationCheck(name="uninstall_registry_scan", status="pass", details=f"Enumerated {len(entries)} uninstall entries."))
    except OSError as exc:
        checks.append(ValidationCheck(name="uninstall_registry_scan", status="fail", details=f"Registry enumeration failed: {exc}"))

    checks.append(
        validate_command(
            "termservice_query",
            ["sc", "query", "TermService"],
            "Windows Service Control Manager responded for TermService.",
            "TermService query failed",
        )
    )
    return checks


def validate_tool_windows(tool: ToolSpec, status: ToolStatus) -> list[ValidationCheck]:
    checks = validate_windows_runtime()
    expected_paths = [expand_path(path) for path in tool.windows_paths]
    checks.append(
        make_check(
            "windows_paths_configured",
            bool(expected_paths) or tool.install_kind == "system_feature",
            f"{len(expected_paths)} Windows path candidates configured." if expected_paths else "Windows built-in feature does not rely on executable paths.",
            "No Windows path candidates configured.",
        )
    )
    checks.append(
        ValidationCheck(
            name="detector_execution",
            status="pass",
            details=f"Status probe completed with label '{status.status_label}'.",
        )
    )

    if tool.install_kind == "system_feature":
        checks.append(
            make_check(
                "settings_uri",
                bool(tool.settings_uri),
                f"Settings URI configured: {tool.settings_uri}",
                "Settings URI missing for Windows Remote Desktop.",
            )
        )
    else:
        checks.append(
            make_check(
                "registry_match_names",
                bool(tool.windows_registry_names),
                f"Registry display-name matchers configured: {', '.join(tool.windows_registry_names)}",
                "Registry display-name matchers missing for Windows detection.",
            )
        )
        if status.installed and status.launch_targets:
            checks.append(ValidationCheck(name="installation_probe", status="pass", details=f"Installed executable detected at {status.launch_targets[0]}"))
        elif status.installed:
            checks.append(ValidationCheck(name="installation_probe", status="warn", details="Tool looks installed from registry metadata, but no launchable executable path was found."))
        else:
            checks.append(ValidationCheck(name="installation_probe", status="pass", details="Tool is not installed on this host, but executable and registry paths were checked."))
    return checks


def summarize_validation(checks: list[ValidationCheck]) -> dict[str, int]:
    summary = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        summary.setdefault(check.status, 0)
        summary[check.status] += 1
    return summary


def status_to_dict(tool: ToolSpec, status: ToolStatus, os_family: str) -> dict[str, object]:
    return {
        "tool_key": tool.key,
        "name": tool.name,
        "category": tool.category,
        "supported_on": list(tool.supported_on),
        "official_source": tool.official_urls.get(os_family),
        "status": asdict(status),
    }


def build_report(catalog: list[ToolSpec], os_family: str) -> dict[str, object]:
    tools: list[dict[str, object]] = []
    aggregate_checks: list[ValidationCheck] = []

    for tool in catalog:
        status = detect_status(tool, os_family)
        checks = validate_tool(tool, os_family, status=status)
        aggregate_checks.extend(checks)
        tools.append(
            {
                **status_to_dict(tool, status, os_family),
                "validation": [asdict(check) for check in checks],
                "validation_summary": summarize_validation(checks),
            }
        )

    return {
        "host": host_metadata(os_family),
        "tools": tools,
        "validation_summary": summarize_validation(aggregate_checks),
        "log_file": ACTIVE_LOG_FILE,
    }


def export_report(report_path: str, catalog: list[ToolSpec], os_family: str) -> str:
    path = Path(report_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(catalog, os_family)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    log_event("report_exported", path=str(path), tool_count=len(catalog), os_family=os_family)
    return str(path)


def human_host_summary(os_family: str) -> str:
    if os_family == "macos":
        version = platform.mac_ver()[0] or "unknown"
        return f"macOS {version}"
    return f"Windows {platform.release() or 'unknown'}"


def print_banner(os_family: str) -> None:
    width = min(shutil.get_terminal_size((96, 24)).columns, 96)
    rule = "=" * width
    print(f"{Style.cyan}{rule}{Style.reset}")
    print(f"{Style.bold}{APP_NAME}{Style.reset}  {APP_TAGLINE}")
    print(f"{Style.dim}Host: {human_host_summary(os_family)} | Python {platform.python_version()} | Official sources only{Style.reset}")
    print(f"{Style.dim}Scope: local install, status, launch, and settings helpers for remote-access tools{Style.reset}")
    print(f"{Style.cyan}{rule}{Style.reset}")


def print_dashboard(catalog: list[ToolSpec], os_family: str) -> None:
    statuses = {tool.key: detect_status(tool, os_family) for tool in catalog}
    print_banner(os_family)
    print(f"{Style.bold}Available tools{Style.reset}")
    print(f"{'No.':<4} {'Tool':<24} {'Category':<12} {'Status':<14} {'Version'}")
    print("-" * 72)
    for index, tool in enumerate(catalog, start=1):
        status = statuses[tool.key]
        version = status.version or "-"
        print(f"{index:<4} {tool.name:<24} {tool.category:<12} {status.status_label:<14} {version}")
    print()


def print_tool_details(tool: ToolSpec, status: ToolStatus, os_family: str) -> None:
    print(f"{Style.bold}{tool.name}{Style.reset}")
    print(textwrap.fill(tool.description, width=88))
    print(f"Status: {status.status_label}")
    if status.version:
        print(f"Version: {status.version}")
    source_url = tool.official_urls.get(os_family)
    if source_url:
        print(f"Official source: {source_url}")
    for detail in status.details:
        print(f"- {detail}")
    for note in tool.notes:
        print(f"- {note}")
    if status.installer_candidate:
        print(f"- Installer candidate in Downloads: {status.installer_candidate}")
    print()


def print_validation_results(title: str, checks: list[ValidationCheck]) -> None:
    summary = summarize_validation(checks)
    print(f"{Style.bold}{title}{Style.reset}")
    print(f"Pass: {summary.get('pass', 0)}  Warn: {summary.get('warn', 0)}  Fail: {summary.get('fail', 0)}")
    for check in checks:
        print(f"- [{check.status.upper()}] {check.name}: {check.details}")
    print()


def print_report_export_message(path: str) -> None:
    print(f"Report exported to {path}")
    print()


def open_url(url: str, allow_browser: bool = True) -> bool:
    if not allow_browser:
        return False
    try:
        return webbrowser.open(url)
    except webbrowser.Error:
        return False


def launch_path(target: str) -> tuple[bool, str]:
    system = platform.system()
    path = expand_path(target)
    try:
        if system == "Darwin":
            subprocess.run(["open", path], check=False)
            return True, f"Opened {path}"
        if system == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
            return True, f"Opened {path}"
    except OSError as exc:
        return False, str(exc)
    return False, f"Unsupported OS for launching path: {system}"


def open_settings(tool: ToolSpec, allow_browser: bool = True) -> tuple[bool, str]:
    if not tool.settings_uri:
        return False, "No settings URI configured."

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", tool.settings_uri], check=False)
            return True, f"Opened settings URI {tool.settings_uri}"
        if system == "Windows":
            if allow_browser:
                os.startfile(tool.settings_uri)  # type: ignore[attr-defined]
                return True, f"Opened settings URI {tool.settings_uri}"
            return False, f"Settings URI not opened because browser/GUI actions are disabled: {tool.settings_uri}"
    except OSError as exc:
        return False, str(exc)
    return False, f"Unsupported OS for settings launch: {system}"


def do_install(tool: ToolSpec, status: ToolStatus, os_family: str, allow_browser: bool = True) -> None:
    log_event("install_requested", tool=tool.key, os_family=os_family, installed=status.installed)
    print_tool_details(tool, status, os_family)
    if tool.install_kind == "system_feature":
        success, message = open_settings(tool, allow_browser=allow_browser)
        log_event("settings_open", tool=tool.key, success=success, mode="install", message=message)
        print(message if success else f"Could not open settings automatically. Use: {tool.settings_uri}")
        return

    source_url = tool.official_urls.get(os_family)
    if status.installed:
        print("This tool already appears to be installed.")
        if status.launch_targets:
            print("Use the launch action if you want to open it.")
        return

    if status.installer_candidate:
        if not sys.stdin.isatty():
            print(f"Installer candidate found: {status.installer_candidate}")
            if source_url and open_url(source_url, allow_browser=allow_browser):
                log_event("source_open", tool=tool.key, success=True, url=source_url)
                print(f"Opened official source: {source_url}")
            else:
                log_event("source_open", tool=tool.key, success=False, url=source_url)
                print(f"Open this official source manually: {source_url}")
            return
        print("A matching installer was found in Downloads.")
        choice = prompt_choice(
            "Choose install action",
            {
                "1": "Launch the local installer",
                "2": "Open the official download page",
                "3": "Do both",
                "0": "Back",
            },
        )
        if choice == "1":
            success, message = launch_path(status.installer_candidate)
            log_event("installer_launch", tool=tool.key, success=success, path=status.installer_candidate, message=message)
            print(message if success else f"Could not launch installer: {message}")
            return
        if choice == "2":
            if source_url and open_url(source_url, allow_browser=allow_browser):
                log_event("source_open", tool=tool.key, success=True, url=source_url)
                print(f"Opened official source: {source_url}")
            else:
                log_event("source_open", tool=tool.key, success=False, url=source_url)
                print(f"Open this official source manually: {source_url}")
            return
        if choice == "3":
            success, message = launch_path(status.installer_candidate)
            log_event("installer_launch", tool=tool.key, success=success, path=status.installer_candidate, message=message)
            print(message if success else f"Could not launch installer: {message}")
            if source_url and open_url(source_url, allow_browser=allow_browser):
                log_event("source_open", tool=tool.key, success=True, url=source_url)
                print(f"Opened official source: {source_url}")
            else:
                log_event("source_open", tool=tool.key, success=False, url=source_url)
                print(f"Open this official source manually: {source_url}")
            return
        return

    if source_url and open_url(source_url, allow_browser=allow_browser):
        log_event("source_open", tool=tool.key, success=True, url=source_url)
        print(f"Opened official source: {source_url}")
    else:
        log_event("source_open", tool=tool.key, success=False, url=source_url)
        print(f"Open this official source manually: {source_url}")


def do_launch(tool: ToolSpec, status: ToolStatus, os_family: str, allow_browser: bool = True) -> None:
    log_event("launch_requested", tool=tool.key, os_family=os_family, installed=status.installed)
    print_tool_details(tool, status, os_family)
    if tool.install_kind == "system_feature":
        success, message = open_settings(tool, allow_browser=allow_browser)
        log_event("settings_open", tool=tool.key, success=success, mode="launch", message=message)
        print(message if success else f"Could not open settings automatically. Use: {tool.settings_uri}")
        if tool.key == "screen-sharing" and status.launch_targets:
            print("The built-in Screen Sharing client is also present if you want to open it separately.")
        return

    if not status.installed:
        print("This tool does not appear to be installed yet. Use the install action first.")
        return

    if not status.launch_targets:
        print("No launch target was found even though the tool looks installed.")
        return

    targets = list(dict.fromkeys(status.launch_targets))
    if len(targets) == 1:
        success, message = launch_path(targets[0])
        log_event("app_launch", tool=tool.key, success=success, target=targets[0], message=message)
        print(message if success else f"Could not launch: {message}")
        return

    if not sys.stdin.isatty():
        success, message = launch_path(targets[0])
        log_event("app_launch", tool=tool.key, success=success, target=targets[0], message=message)
        print(message if success else f"Could not launch: {message}")
        return

    options = {str(index): target for index, target in enumerate(targets, start=1)}
    options["0"] = "Back"
    choice = prompt_choice("Multiple launch targets detected", options)
    if choice == "0":
        return
    success, message = launch_path(options[choice])
    log_event("app_launch", tool=tool.key, success=success, target=options[choice], message=message)
    print(message if success else f"Could not launch: {message}")


def do_source(tool: ToolSpec, os_family: str, allow_browser: bool = True) -> None:
    source_url = tool.official_urls.get(os_family)
    if not source_url:
        print("No official source is configured for this OS.")
        log_event("source_open", tool=tool.key, success=False, reason="missing_source")
        return
    if open_url(source_url, allow_browser=allow_browser):
        log_event("source_open", tool=tool.key, success=True, url=source_url)
        print(f"Opened official source: {source_url}")
    else:
        log_event("source_open", tool=tool.key, success=False, url=source_url)
        print(f"Open this official source manually: {source_url}")


def do_validate(tool: ToolSpec, os_family: str) -> None:
    status = detect_status(tool, os_family)
    print_tool_details(tool, status, os_family)
    checks = validate_tool(tool, os_family, status=status)
    log_event("tool_validated", tool=tool.key, os_family=os_family, summary=summarize_validation(checks))
    print_validation_results(f"{tool.name} Validation", checks)


def do_validate_all(catalog: list[ToolSpec], os_family: str) -> None:
    all_checks: list[ValidationCheck] = []
    for tool in catalog:
        status = detect_status(tool, os_family)
        checks = validate_tool(tool, os_family, status=status)
        all_checks.extend(checks)
        print_validation_results(f"{tool.name} Validation", checks)
    log_event("catalog_validated", os_family=os_family, summary=summarize_validation(all_checks))


def do_export_report(catalog: list[ToolSpec], os_family: str, report_path: str | None = None) -> str:
    resolved_path = report_path or default_report_path()
    exported = export_report(resolved_path, catalog, os_family)
    print_report_export_message(exported)
    return exported


def print_best_practices() -> None:
    print(f"{Style.bold}Best Practices{Style.reset}")
    practices = [
        "Install from the vendor's official source and verify the product name before launching an installer.",
        "Use attended access by default; reserve unattended access for machines you own and maintain.",
        "Turn on MFA, strong passwords, and device naming conventions so hosts are easy to identify and audit.",
        "Review OS permissions for screen recording, accessibility, and file access before troubleshooting failures.",
        "Disable or remove remote-access software you are not actively using to reduce attack surface.",
        "Document which tool is approved for which environment instead of mixing multiple remote-control stacks without a reason.",
    ]
    for practice in practices:
        print(f"- {practice}")
    print()


def print_embedded_help() -> None:
    print(f"{Style.bold}Help{Style.reset}")
    help_text = f"""
    {APP_NAME} is a single-file local admin helper for mainstream remote-access tools.

    Interactive mode:
      python3 relaydeck.py

    Common command-line examples:
      python3 relaydeck.py --list
      python3 relaydeck.py --tool teamviewer --action status
      python3 relaydeck.py --tool anydesk --action install
      python3 relaydeck.py --tool realvnc --action validate
      python3 relaydeck.py --tool screen-sharing --action launch
      python3 relaydeck.py --validate
      python3 relaydeck.py --export-report ./relaydeck-report.json
      python3 relaydeck.py --best-practices

    Actions:
      status   Show installation and service details.
      install  Open the official source, or launch a matching installer already in Downloads.
      launch   Open the installed app or the system settings page for built-in services.
      source   Open only the official vendor or platform page.
      validate Check that the detection and management probes for the selected tool are healthy.

    Notes:
      - The script does not silently enable remote access or bypass local OS prompts.
      - Built-in services are managed through the relevant system settings pages.
      - Validation mode is the fastest way to smoke-test the Windows branch on a real Windows machine.
      - Every run writes an operational log file unless you override the destination.
    """
    print(textwrap.dedent(help_text).strip())
    print()


def prompt_choice(title: str, options: dict[str, str]) -> str:
    print(f"{Style.bold}{title}{Style.reset}")
    for key, label in options.items():
        print(f"[{key}] {label}")
    while True:
        choice = input("> ").strip()
        if choice in options:
            return choice
        print("Choose one of the listed options.")


def choose_tool(catalog: list[ToolSpec], statuses: dict[str, ToolStatus], prompt_text: str) -> ToolSpec | None:
    print(f"{Style.bold}{prompt_text}{Style.reset}")
    for index, tool in enumerate(catalog, start=1):
        status = statuses[tool.key]
        summary = status.version or status.status_label
        print(f"[{index}] {tool.name:<24} {summary}")
    print("[0] Back")
    while True:
        raw = input("> ").strip()
        if raw == "0":
            return None
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(catalog):
                return catalog[index]
        print("Choose a valid tool number.")


def interactive_loop(catalog: list[ToolSpec], os_family: str) -> None:
    while True:
        statuses = {tool.key: detect_status(tool, os_family) for tool in catalog}
        print_dashboard(catalog, os_family)
        choice = prompt_choice(
            "Main Menu",
            {
                "1": "Inspect tool status",
                "2": "Install from official source",
                "3": "Launch or open settings",
                "4": "Validate environment",
                "5": "Export JSON report",
                "6": "Best practices",
                "7": "Help",
                "0": "Exit",
            },
        )
        print()
        if choice == "0":
            log_event("interactive_exit", os_family=os_family)
            return
        if choice == "4":
            do_validate_all(catalog, os_family)
            continue
        if choice == "5":
            do_export_report(catalog, os_family)
            continue
        if choice == "6":
            print_best_practices()
            continue
        if choice == "7":
            print_embedded_help()
            continue

        selected = choose_tool(catalog, statuses, "Pick a tool")
        if selected is None:
            print()
            continue

        status = statuses[selected.key]
        if choice == "1":
            print_tool_details(selected, status, os_family)
        elif choice == "2":
            do_install(selected, status, os_family)
        elif choice == "3":
            do_launch(selected, status, os_family)
        print()


def filter_catalog_for_os(catalog: list[ToolSpec], os_family: str) -> list[ToolSpec]:
    return [tool for tool in catalog if os_family in tool.supported_on]


def run_non_interactive(args: argparse.Namespace, catalog: list[ToolSpec], os_family: str) -> bool:
    handled = False
    if args.best_practices:
        print_best_practices()
        handled = True
    if args.help_menu:
        print_embedded_help()
        handled = True
    if args.validate:
        do_validate_all(catalog, os_family)
        handled = True
    if args.list:
        print_dashboard(catalog, os_family)
        handled = True

    if args.tool:
        selected = next((tool for tool in catalog if tool.key == args.tool), None)
        if selected is None:
            raise SystemExit(f"Unknown tool: {args.tool}")

        status = detect_status(selected, os_family)
        if args.action == "status":
            print_tool_details(selected, status, os_family)
        elif args.action == "install":
            do_install(selected, status, os_family, allow_browser=not args.no_browser)
        elif args.action == "launch":
            do_launch(selected, status, os_family, allow_browser=not args.no_browser)
        elif args.action == "validate":
            do_validate(selected, os_family)
        elif args.action == "source":
            do_source(selected, os_family, allow_browser=not args.no_browser)
        else:
            raise SystemExit(f"Unsupported action: {args.action}")
        handled = True

    if args.export_report:
        do_export_report(catalog, os_family, args.export_report)
        handled = True

    return handled


def parse_args(tool_keys: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="relaydeck.py",
        description="Single-file remote-access installer and manager for macOS and Windows.",
    )
    parser.add_argument("--list", action="store_true", help="List supported tools for the current OS.")
    parser.add_argument("--tool", choices=tool_keys, help="Tool key to target for a non-interactive action.")
    parser.add_argument(
        "--action",
        choices=("status", "install", "launch", "source", "validate"),
        default="status",
        help="Action to run with --tool.",
    )
    parser.add_argument("--best-practices", action="store_true", help="Print operating guidance for safe deployments.")
    parser.add_argument("--validate", action="store_true", help="Validate all configured tools and host probes for the current OS.")
    parser.add_argument("--export-report", help="Write a JSON report with host metadata, tool status, and validation details.")
    parser.add_argument("--help-menu", action="store_true", help="Print the in-app help screen and exit.")
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE, help=f"Write operational logs to this file. Default: {DEFAULT_LOG_FILE}")
    parser.add_argument("--verbose", action="store_true", help="Also mirror log output to stderr.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser or settings URIs automatically.")
    return parser.parse_args()


def main() -> int:
    os_family = detect_os_family()
    catalog = filter_catalog_for_os(build_catalog(), os_family)
    args = parse_args([tool.key for tool in catalog])
    configure_logging(args.log_file, verbose=args.verbose)
    log_event("startup", os_family=os_family, host=socket.gethostname(), log_file=args.log_file)
    handled = run_non_interactive(args, catalog, os_family)
    if not handled:
        log_event("interactive_start", os_family=os_family, tool_count=len(catalog))
        interactive_loop(catalog, os_family)
    log_event("shutdown", os_family=os_family)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
