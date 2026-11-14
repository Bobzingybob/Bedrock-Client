"""options.txt management for Minecraft Bedrock."""
import glob
import os
import shutil
from pathlib import Path


OPTIONS_GLOBS = [
    # Microsoft Store UWP (highest priority — this is what the launcher uses)
    os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.MinecraftUWP_8wekyb3d8bbwe"
                       r"\LocalState\games\com.mojang\minecraftpe\options.txt"),
    # Standard Bedrock (APPDATA)
    os.path.expandvars(r"%APPDATA%\Minecraft Bedrock\Users\*\games\com.mojang\minecraftpe\options.txt"),
    # LeviLauncher GDK instances (fallback — only if launching via LeviLauncher)
    os.path.expandvars(r"%LOCALAPPDATA%\LeviLauncher\Instances\*\Minecraft Bedrock\Users\*\games\com.mojang\minecraftpe\options.txt"),
]


def find_levilauncher_instance():
    """Find the active LeviLauncher instance directory.
    
    Returns the Path to the instance root (e.g. .../LeviLauncher/Instances/My 1.26.63.01 Instance/)
    or None if no instance is found.
    """
    levi_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "LeviLauncher" / "Instances"
    if not levi_dir.exists():
        return None
    
    # Find the most recently modified instance directory
    instances = list(levi_dir.iterdir())
    instances = [d for d in instances if d.is_dir()]
    if not instances:
        return None
    
    return max(instances, key=lambda d: d.stat().st_mtime)


def find_options():
    """Locate the most recent options.txt file.
    
    Prioritizes Microsoft Store UWP over LeviLauncher GDK instances,
    since the launcher uses Microsoft Store for Xbox Live support.
    """
    found = [p for g in OPTIONS_GLOBS for p in glob.glob(g)]
    if not found:
        return None
    
    # Prefer Microsoft Store UWP over LeviLauncher instances
    uwp_options = [p for p in found if "Microsoft.MinecraftUWP" in str(p)]
    if uwp_options:
        return Path(max(uwp_options, key=os.path.getmtime))
    
    return Path(max(found, key=os.path.getmtime))


def apply_options(profile, dry=False):
    """Apply a profile dictionary to options.txt, backing up first.
    
    Modifies existing keys and adds missing keys from the profile.
    Returns (changed_keys, missing_keys) tuple.
    """
    path = find_options()
    if not path:
        print("[!] options.txt not found - launch the game once first.")
        return [], []
    
    print(f"[i] using {path}")
    
    # Read current options
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    
    # Parse existing keys
    existing_keys = {}
    for line in lines:
        key, sep, val = line.partition(":")
        if sep:
            existing_keys[key] = val
    
    # Determine what to change and what to add
    changed = []
    new_lines = []
    for line in lines:
        key, sep, _ = line.partition(":")
        if sep and key in profile:
            line = f"{key}:{profile[key]}"
            changed.append(key)
        new_lines.append(line)
    
    # Add missing keys
    missing = set(profile) - set(changed)
    for key in missing:
        new_lines.append(f"{key}:{profile[key]}")
        changed.append(key)
    
    if not dry:
        shutil.copy2(path, path.with_suffix(".txt.bak"))
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    
    print(f"[+] options.txt {'would change' if dry else 'updated'}: {', '.join(changed) or 'nothing'}")
    return changed, missing
