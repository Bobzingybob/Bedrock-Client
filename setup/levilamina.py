"""LeviLamina and LeviOptimize setup via LeviLauncher CLI."""
import subprocess
from pathlib import Path

from setup.levilauncher import find_levilauncher, cli, mod_install


def find_lip():
    """Find the lip (LeviLamina Package Manager) executable.
    
    lip is installed alongside LeviLamina in the Bedrock version directory.
    
    Returns Path to lip.exe or None.
    """
    # lip is typically in the Bedrock version directory
    # Check common locations
    search_paths = [
        Path(__import__("os").environ.get("LOCALAPPDATA", "")) / "LeviLauncher" / "versions",
        Path(__import__("os").environ.get("APPDATA", "")) / "LeviLauncher" / "versions",
    ]
    
    for base in search_paths:
        if base.exists():
            for version_dir in base.iterdir():
                lip = version_dir / "lip.exe"
                if lip.exists():
                    return lip
    
    return None


def install_levioptimize_client(exe=None):
    """Install LeviOptimize client mod.
    
    Uses LeviLauncher CLI: mod install github.com/LiteLDev/LeviOptimize#client
    Or lip: lip install github.com/LiteLDev/LeviOptimize#client
    
    Args:
        exe: Path to LeviLauncher.exe (auto-detected if None)
        
    Returns True on success.
    """
    if exe is None:
        exe = find_levilauncher()
    
    if not exe:
        print("[!] LeviLauncher not found - install LeviLauncher first")
        return False
    
    mod_url = "github.com/LiteLDev/LeviOptimize#client"
    print("[i] installing LeviOptimize (client)...")
    
    if mod_install(exe, mod_url):
        print("[+] LeviOptimize client installed")
        return True
    
    # Fallback: try lip directly
    lip = find_lip()
    if lip:
        print("[i] trying lip directly...")
        result = subprocess.run(
            [str(lip), "install", mod_url],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("[+] LeviOptimize client installed via lip")
            return True
        else:
            print(f"[!] lip install failed: {result.stderr.strip()}")
    
    print("[!] Failed to install LeviOptimize")
    print("[i] Manual installation:")
    print(f"   1. Run: {exe} mod install {mod_url}")
    print("   2. Or use lip in your Bedrock version directory")
    return False


def verify_levioptimize():
    """Check if LeviOptimize is installed.
    
    Looks for LeviOptimize files in the Bedrock version directory.
    
    Returns True if installed.
    """
    search_paths = [
        Path(__import__("os").environ.get("LOCALAPPDATA", "")) / "LeviLauncher" / "versions",
        Path(__import__("os").environ.get("APPDATA", "")) / "LeviLauncher" / "versions",
    ]
    
    for base in search_paths:
        if base.exists():
            for version_dir in base.iterdir():
                # Check for LeviOptimize in mods folder
                mods_dir = version_dir / "mods"
                if mods_dir.exists():
                    for item in mods_dir.iterdir():
                        if "levioptimize" in item.name.lower():
                            return True
    
    return False


def install_all(exe=None):
    """Install all LeviLamina-related mods.
    
    Args:
        exe: Path to LeviLauncher.exe (auto-detected if None)
        
    Returns True if all mods installed successfully.
    """
    if exe is None:
        exe = find_levilauncher()
    
    if not exe:
        print("[!] LeviLauncher not found")
        return False
    
    success = True
    
    # Install LeviOptimize
    if not verify_levioptimize():
        if not install_levioptimize_client(exe):
            success = False
    else:
        print("[i] LeviOptimize already installed")
    
    return success
