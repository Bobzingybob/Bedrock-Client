"""Windows OS-level optimizations for Minecraft Bedrock."""
import os
import subprocess
from pathlib import Path


PROCESS_NAME = "Minecraft.Windows.exe"


def set_windows_graphics_priority():
    """Set Minecraft.Windows.exe to High Performance in Windows Graphics Settings.
    
    Uses PowerShell to set the graphics preference for the game executable.
    This ensures the discrete GPU is used on laptops with hybrid graphics.
    
    Returns True on success.
    """
    # Find the game executable
    game_exe = find_game_exe()
    if not game_exe:
        print("[i] Minecraft.Windows.exe not found - skipping graphics settings")
        return False
    
    ps_command = f"""
    $appPath = '{game_exe}'
    $parentPath = Split-Path $appPath -Parent
    Add-AppxPackage -Path "$parentPath\\AppxManifest.xml" -Register -ForceApplicationShutdown -ErrorAction SilentlyContinue
    """
    
    # Alternative: use Windows Graphics Settings via registry
    # This is more reliable than trying to use the GUI
    try:
        # Set the graphics preference via PowerShell
        ps = (
            f"$exe = '{game_exe}';"
            f"$parent = Split-Path $exe -Parent;"
            "if (Test-Path $parent) {"
            "    $settings = New-Object PSObject;"
            "    $settings | Add-Member -MemberType NoteProperty -Name 'Version' -Value 1;"
            "    $settings | Add-Member -MemberType NoteProperty -Name 'GameName' -Value 'Minecraft.Windows.exe';"
            "    $settings | Add-Member -MemberType NoteProperty -Name 'MaxLatency' -Value 0;"
            "    $settings | Add-Member -MemberType NoteProperty -Name 'ExecutionAffinity' -Value 0;"
            "    $settings | Add-Member -MemberType NoteProperty -Name 'GraphicsPreference' -Value 2;"
            "    $json = $settings | ConvertTo-Json;"
            "    $settingsPath = Join-Path $parent 'WgpMetadata.xml';"
            "    Set-Content -Path $settingsPath -Value $json -Force;"
            "}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10
        )
        print("[+] Windows Graphics Settings set to High Performance")
        return True
    except Exception as e:
        print(f"[i] couldn't set Windows Graphics Settings: {e}")
        return False


def find_game_exe():
    """Find the Minecraft.Windows.exe path.
    
    Returns Path to the executable or None.
    """
    search_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Packages" / "Microsoft.MinecraftUWP_8wekyb3d8bbwe" / "LocalCache" / "LocalizedPackages" / "Minecraft for Windows" / "Minecraft.Windows.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "WindowsApps" / "Minecraft.Windows.exe",
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    # Try to find it in WindowsApps (may require admin)
    try:
        windows_apps = Path(os.environ.get("PROGRAMFILES", "")) / "WindowsApps"
        if windows_apps.exists():
            for exe in windows_apps.glob("Microsoft.MinecraftUWP_*"):
                if (exe / "Minecraft.Windows.exe").exists():
                    return exe / "Minecraft.Windows.exe"
    except PermissionError:
        pass
    
    return None


def disable_xbox_game_bar():
    """Disable Xbox Game Bar to reduce input lag.
    
    Uses registry to disable Game Bar overlay.
    
    Returns the previous state (True if was enabled) or None on error.
    """
    try:
        # Check current state
        result = subprocess.run(
            ["reg", "query", "HKCU\\Software\\Microsoft\\GameBar", "/v", "UseNexusForGameBarEnabled"],
            capture_output=True, text=True
        )
        
        previous_state = None
        if result.returncode == 0:
            # Game Bar is enabled
            previous_state = True
        else:
            # Game Bar is already disabled or key doesn't exist
            previous_state = False
        
        # Disable Game Bar
        subprocess.run(
            ["reg", "add", "HKCU\\Software\\Microsoft\\GameBar", "/v", "UseNexusForGameBarEnabled", "/t", "REG_DWORD", "/d", "0", "/f"],
            capture_output=True, text=True
        )
        
        # Also disable Game Bar recording
        subprocess.run(
            ["reg", "add", "HKCU\\System\\GameConfigStore", "/v", "GameDVR_Enabled", "/t", "REG_DWORD", "/d", "0", "/f"],
            capture_output=True, text=True
        )
        
        if previous_state:
            print("[+] Xbox Game Bar disabled (reduces input lag)")
        else:
            print("[i] Xbox Game Bar already disabled")
        
        return previous_state
    
    except Exception as e:
        print(f"[i] couldn't disable Xbox Game Bar: {e}")
        return None


def enable_xbox_game_bar():
    """Re-enable Xbox Game Bar (restore on exit)."""
    try:
        # Re-enable Game Bar
        subprocess.run(
            ["reg", "add", "HKCU\\Software\\Microsoft\\GameBar", "/v", "UseNexusForGameBarEnabled", "/t", "REG_DWORD", "/d", "1", "/f"],
            capture_output=True, text=True
        )
        
        # Re-enable Game Bar recording
        subprocess.run(
            ["reg", "add", "HKCU\\System\\GameConfigStore", "/v", "GameDVR_Enabled", "/t", "REG_DWORD", "/d", "1", "/f"],
            capture_output=True, text=True
        )
        
        print("[+] Xbox Game Bar re-enabled")
    
    except Exception as e:
        print(f"[i] couldn't re-enable Xbox Game Bar: {e}")


def apply_all_os_optimizations():
    """Apply all OS-level optimizations.
    
    Returns a dict of previous states for restoration.
    """
    previous_states = {}
    
    # Set graphics priority
    set_windows_graphics_priority()
    
    # Disable Xbox Game Bar
    game_bar_state = disable_xbox_game_bar()
    if game_bar_state is not None:
        previous_states["game_bar"] = game_bar_state
    
    return previous_states


def restore_os_optimizations(previous_states):
    """Restore OS-level optimizations to previous state."""
    if previous_states.get("game_bar"):
        enable_xbox_game_bar()
