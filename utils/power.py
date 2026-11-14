"""Power plan management for Windows."""
import re
import subprocess


HIGH_PERF_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"


def active_power_plan():
    """Get the GUID of the currently active power plan."""
    out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True).stdout
    m = re.search(r"([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})", out, re.I)
    return m.group(1) if m else None


def set_power_plan(guid):
    """Set the active power plan by GUID. Returns True on success."""
    return subprocess.run(["powercfg", "/setactive", guid], capture_output=True).returncode == 0


def set_high_performance():
    """Switch to High Performance power plan. Returns the previous plan GUID or None."""
    previous = active_power_plan()
    if set_power_plan(HIGH_PERF_GUID):
        print("[+] High performance power plan active")
        return previous
    else:
        print("[i] couldn't set High performance plan (may not exist on this PC)")
        return None


def restore_power_plan(guid):
    """Restore a previously saved power plan."""
    if guid and set_power_plan(guid):
        print("[+] power plan restored")
        return True
    return False
