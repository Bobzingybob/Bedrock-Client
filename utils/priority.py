"""CPU priority management for Minecraft Bedrock."""
import psutil


PROCESS_NAME = "Minecraft.Windows.exe"


def game_running():
    """Check if Minecraft Bedrock is currently running."""
    return any(p.info["name"] == PROCESS_NAME for p in psutil.process_iter(["name"]))


def wait_for_game(timeout=90):
    """Wait for Minecraft Bedrock to start. Returns the process or None."""
    import time
    end = time.time() + timeout
    while time.time() < end:
        for p in psutil.process_iter(["name"]):
            if p.info["name"] == PROCESS_NAME:
                return p
        time.sleep(1)
    return None


def set_high_priority(process):
    """Set a process's CPU priority to High. Returns True on success."""
    try:
        process.nice(psutil.HIGH_PRIORITY_CLASS)
        print("[+] game priority set to High")
        return True
    except psutil.AccessDenied:
        print("[i] priority change denied - run from an admin terminal")
        return False
