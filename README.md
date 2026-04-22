# RelayDeck

## IMPORTANT, READ BEFORE INSTALL OR RUN

Because it involves the installation and management of administrative tools, this tool must be run with `sudo` on macOS systems. Example:

```
sudo python3 relaydeck.py
```

**RelayDeck** is a single-file remote access installer and manager for local administration on **macOS** and **Windows**.

It gives you one clean entrypoint to:

- Detect the host OS automatically.
- Inspect the status of supported remote-access tools.
- Open official vendor download pages.
- Reuse matching installers already found in `Downloads`.
- Open the right system settings for built-in remote-access features.
- Validate the local environment before rollout.
- Export JSON reports for audits, support handoff, or troubleshooting.
- Keep an operational log of actions taken by the tool.

If you want a practical, no-dependency helper that feels closer to an admin console than a throwaway script, that is the point of RelayDeck.

## Why RelayDeck

Remote-access tooling is usually fragmented:

- one workflow to install TeamViewer
- another to check AnyDesk
- another to review VNC presence
- another to find native macOS or Windows remote settings

RelayDeck pulls those routine tasks into **one script**, with **official-source-first behavior**, a **clean interactive menu**, and a **CLI mode** for faster repeatable checks.

## Supported Platforms

- macOS
- Windows

## Supported Tools

- TeamViewer
- AnyDesk
- RealVNC Connect
- macOS Screen Sharing
- Windows Remote Desktop

## Design Principles

- **Single file**: run one Python script, no external packages required.
- **Official sources only**: opens vendor or platform pages instead of relying on random mirrors.
- **Local admin helper**: the script helps install, inspect, launch, validate, and report.
- **No silent bypasses**: it does not secretly enable unattended access or skip OS permission flows.
- **Cross-platform intent**: one interface, OS-aware behavior underneath.

## Recommended Start

If you are trying RelayDeck for the first time, this is the best sequence:

1. Run validation.
2. Review the detected tools.
3. Open the interactive menu.
4. Export a report if you want a record of the current machine state.

### macOS / Linux-style shell

```bash
python3 relaydeck.py --validate
python3 relaydeck.py --list
python3 relaydeck.py
python3 relaydeck.py --export-report ./relaydeck-report.json
```

### Windows

```powershell
py relaydeck.py --validate
py relaydeck.py --list
py relaydeck.py
py relaydeck.py --export-report .\relaydeck-report.json
```

## Quick Start

Clone the repository and run the script from the project folder:

```bash
python3 relaydeck.py
```

On Windows you can also use:

```powershell
py relaydeck.py
```

RelayDeck uses only the Python standard library, so there is no setup step like `pip install -r requirements.txt`.

## Main Usage Modes

### 1. Interactive Menu

The recommended human-friendly mode:

```bash
python3 relaydeck.py
```

The main menu lets you:

- inspect tool status
- install from an official source
- launch installed tools or open the right settings page
- validate the environment
- export a JSON report
- review best practices
- open the built-in help screen

### 2. Fast CLI Commands

Useful for repeatable checks and scripted workflows.

List supported tools for the current OS:

```bash
python3 relaydeck.py --list
```

Show built-in help:

```bash
python3 relaydeck.py --help-menu
```

Show best practices:

```bash
python3 relaydeck.py --best-practices
```

Validate all supported tools on the current machine:

```bash
python3 relaydeck.py --validate
```

Export a JSON report:

```bash
python3 relaydeck.py --export-report ./relaydeck-report.json
```

## Tool-Specific Commands

### Status

```bash
python3 relaydeck.py --tool teamviewer --action status
python3 relaydeck.py --tool anydesk --action status
python3 relaydeck.py --tool realvnc --action status
python3 relaydeck.py --tool screen-sharing --action status
```

### Install

```bash
python3 relaydeck.py --tool teamviewer --action install
python3 relaydeck.py --tool anydesk --action install
python3 relaydeck.py --tool realvnc --action install
python3 relaydeck.py --tool screen-sharing --action install
```

### Launch

```bash
python3 relaydeck.py --tool teamviewer --action launch
python3 relaydeck.py --tool anydesk --action launch
python3 relaydeck.py --tool realvnc --action launch
python3 relaydeck.py --tool screen-sharing --action launch
```

### Open Official Source Only

```bash
python3 relaydeck.py --tool teamviewer --action source
python3 relaydeck.py --tool anydesk --action source
python3 relaydeck.py --tool realvnc --action source
```

### Validate One Tool

```bash
python3 relaydeck.py --tool teamviewer --action validate
python3 relaydeck.py --tool realvnc --action validate
```

## Logging and Reporting

Every run writes an operational log unless you override the destination.

Use a custom log file:

```bash
python3 relaydeck.py --log-file ./relaydeck.log
```

Mirror log output to stderr while still writing the file:

```bash
python3 relaydeck.py --log-file ./relaydeck.log --verbose
```

Export a report and run another command in the same invocation:

```bash
python3 relaydeck.py --tool teamviewer --action status --export-report ./relaydeck-report.json
```

The JSON report includes:

- host metadata
- detected tool status
- validation results
- aggregate validation summary
- active log-file path

## Recommended Workflows

### New machine review

```bash
python3 relaydeck.py --validate
python3 relaydeck.py --list
python3 relaydeck.py --export-report ./baseline.json
```

### Help desk check

```bash
python3 relaydeck.py --tool teamviewer --action status
python3 relaydeck.py --tool anydesk --action status
python3 relaydeck.py --tool realvnc --action status
```

### Native macOS remote access check

```bash
python3 relaydeck.py --tool screen-sharing --action status
python3 relaydeck.py --tool screen-sharing --action launch
```

### Windows rollout smoke test

```powershell
py relaydeck.py --validate
py relaydeck.py --tool windows-rdp --action validate
```

## Safety Notes

- RelayDeck is designed for **legitimate local administration** and support workflows.
- It does **not** silently turn on remote access behind the user's back.
- Built-in OS features are handled through the appropriate settings panels.
- You should still review vendor security settings, MFA options, device naming, and unattended-access policies before production use.

## Repository Contents

- `relaydeck.py`: the full application
- `README.md`: project documentation

Generated logs and JSON reports are runtime artifacts and usually should not be committed.

## Feedback

If you publish this on GitHub, ask people for feedback in a structured way:

- report bugs with the OS, tool name, and exact command used
- suggest new supported remote-access tools
- share screenshots of confusing menu flows
- attach exported JSON reports when reporting detection problems
- describe whether the issue happened on macOS or Windows

Good GitHub sections to enable:

- **Issues** for bugs and feature requests
- **Discussions** for ideas, roadmap input, and deployment stories

## Positioning

RelayDeck is valuable because it removes friction from a common real-world admin problem:

**too many remote-access tools, too many install paths, too many settings pages, and not enough consistency**

RelayDeck gives that process one name, one script, and one interface.
