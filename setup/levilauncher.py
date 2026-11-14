"""LeviLauncher detection, installation, and CLI integration."""
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import urllib.request
except ImportError:
    urllib = None


SCRIPT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SCRIPT_DIR / "config.json"


def load_config():
    """Load launcher configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_levilauncher():
    """Detect LeviLauncher installation.
    
    Checks:
    1. config.json install_dir
    2. PATH
    3. Common install locations
    
    Returns Path to LeviLauncher.exe or None.
    """
    config = load_config()
    
    # Check config first
    install_dir = config.get("levilauncher", {}).get("install_dir")
    if install_dir:
        exe = Path(install_dir) / "LeviLauncher.exe"
        if exe.exists():
            return exe
        # Also check relative to script directory
        exe = SCRIPT_DIR / install_dir / "LeviLauncher.exe"
        if exe.exists():
            return exe
    
    # Check project directory (LeviLauncher folder next to the script)
    exe = SCRIPT_DIR / "LeviLauncher" / "LeviLauncher.exe"
    if exe.exists():
        return exe
    
    # Check PATH
    for directory in os.environ.get("PATH", "").split(";"):
        exe = Path(directory) / "LeviLauncher.exe"
        if exe.exists():
            return exe
    
    # Check common locations
    common_locations = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "LeviLauncher" / "LeviLauncher.exe",
        Path(os.environ.get("APPDATA", "")) / "LeviLauncher" / "LeviLauncher.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "LeviLauncher" / "LeviLauncher.exe",
    ]
    for loc in common_locations:
        if loc.exists():
            return loc
    
    return None


def download_levilauncher():
    """Download LeviLauncher portable from GitHub Releases.
    
    Prefers the portable LeviLauncher.exe over the installer to avoid
    interactive installation steps.
    
    Returns Path to downloaded LeviLauncher.exe or None on failure.
    """
    if urllib is None:
        print("[!] urllib not available - cannot download LeviLauncher")
        return None
    
    config = load_config()
    release_api = config.get("levilauncher", {}).get("release_api")
    if not release_api:
        print("[!] No release API URL configured for LeviLauncher")
        return None
    
    print("[i] fetching LeviLauncher release info...")
    try:
        req = urllib.request.Request(release_api)
        with urllib.request.urlopen(req, timeout=30) as response:
            release = json.loads(response.read().decode("utf-8"))
        
        # Prefer the portable LeviLauncher.exe (not the installer)
        asset = None
        for a in release.get("assets", []):
            if a["name"] == "LeviLauncher.exe":
                asset = a
                break
        
        # Fallback to any .exe if portable not found
        if asset is None:
            for a in release.get("assets", []):
                if a["name"].endswith(".exe") and "installer" not in a["name"].lower():
                    asset = a
                    break
        
        # Last resort: any .exe
        if asset is None:
            for a in release.get("assets", []):
                if a["name"].endswith(".exe"):
                    asset = a
                    break
        
        if not asset:
            print("[!] No .exe asset found in LeviLauncher release")
            return None
        
        download_url = asset["browser_download_url"]
        download_name = asset["name"]
        print(f"[i] downloading {download_name}...")
        
        # Download to script directory
        dest = SCRIPT_DIR / download_name
        urllib.request.urlretrieve(download_url, str(dest))
        print(f"[+] LeviLauncher downloaded to {dest}")
        return dest
    
    except Exception as e:
        print(f"[!] Failed to download LeviLauncher: {e}")
        return None


def install_levilauncher():
    """Download LeviLauncher portable executable.
    
    Downloads the portable LeviLauncher.exe directly (no installer needed).
    
    Returns Path to LeviLauncher.exe or None on failure.
    """
    exe = download_levilauncher()
    if not exe:
        return None
    
    print("[+] LeviLauncher ready (portable version, no installation needed)")
    
    # Update config with install directory
    config = load_config()
    config.setdefault("levilauncher", {})
    config["levilauncher"]["install_dir"] = str(exe.parent)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    
    return exe


def cli(exe, *args, capture=True):
    """Run a LeviLauncher CLI command.
    
    Args:
        exe: Path to LeviLauncher.exe
        *args: CLI arguments
        capture: Whether to capture output
        
    Returns:
        subprocess.CompletedProcess or None
    """
    cmd = [str(exe)] + list(args)
    print(f"[i] running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=False
        )
        if result.stdout and capture:
            print(result.stdout.strip())
        if result.returncode != 0 and capture and result.stderr:
            print(f"[!] LeviLauncher error: {result.stderr.strip()}")
        return result
    except FileNotFoundError:
        print(f"[!] LeviLauncher not found at {exe}")
        return None


def get_latest_supported_version(exe):
    """Query LeviLauncher for the latest Bedrock version supported by LeviLamina.
    
    Uses: LeviLauncher.exe installer search --loader
    
    Returns the version string (e.g. "1.26.60.05") or None on failure.
    """
    result = cli(exe, "installer", "search", "--loader", capture=True)
    if result and result.returncode == 0 and result.stdout:
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            # First line is the header, second line is the latest supported version
            parts = lines[1].split()
            if parts:
                return parts[0]
    return None


def ensure_logged_in(exe):
    """Check if a Microsoft account is logged in, and prompt login if not.
    
    LeviLauncher requires a signed-in Microsoft account that owns Minecraft
    to install GDK builds (needed for mods like LeviOptimize).
    
    The Windows account picker requires an interactive desktop session and may not
    work when the script is run from certain contexts (IDE terminals, remote sessions,
    etc.). In those cases, the user must log in manually first.
    
    Returns True if logged in, False if login failed or was skipped.
    """
    # Check if already logged in
    result = subprocess.run(
        [str(exe), "account", "status"],
        capture_output=True, text=True, check=False
    )
    if result.returncode == 0 and "Not signed in" not in result.stdout:
        print("[+] Microsoft account already logged in")
        return True

    # Need to log in — try the CLI login first, then fall back to GUI method
    print("[i] No Microsoft account logged in.")
    print("[i] Attempting sign-in...")
    print()

    # Try the CLI login method first
    try:
        login_process = subprocess.Popen(
            [str(exe), "account", "login"],
            creationflags=0x00000010,  # CREATE_NEW_CONSOLE
            cwd=str(exe.parent)
        )
    except Exception as e:
        print(f"[!] Failed to open login window: {e}")
        print("[i] Please sign in manually through the LeviLauncher GUI instead.")
        return _prompt_manual_login_gui(exe)

    print("[i] A sign-in window should appear — select your Microsoft account.")
    print("[i] Once signed in, close any opened windows and press Enter here to continue.")
    print()
    
    try:
        response = input("[i] Press Enter after signing in (or type 'skip' to continue without mods)...").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n[i] Login cancelled")
        return False

    if response == "skip":
        print("[i] Skipping Microsoft login — engine-level mods will not be available.")
        print("[i] The launcher will still work with options.txt and OS optimizations.")
        return False

    # Give the process a moment to finish writing auth data
    time.sleep(1)

    # Now check if login was successful
    result = subprocess.run(
        [str(exe), "account", "status"],
        capture_output=True, text=True, check=False
    )
    if result.returncode == 0 and "Not signed in" not in result.stdout:
        print("[+] Microsoft account logged in successfully")
        return True
    else:
        # Check for specific auth failure errors
        stderr_output = result.stderr if result.stderr else ""
        stdout_output = result.stdout if result.stdout else ""
        
        if "ERR_AUTH_FAILED" in stderr_output or "ERR_AUTH_FAILED" in stdout_output:
            print("[!] Sign-in failed with ERR_AUTH_FAILED.")
            print()
            print("[i] This is a known issue with the Windows Account Manager (WAM).")
            print("[i] The command-line login method does not work on your system.")
            print()
            return _prompt_manual_login_gui(exe)
        else:
            print("[!] Login not detected — the sign-in may not have completed.")
            print()
            print("[i] The Windows account picker requires an interactive desktop session.")
            print("[i] If you are running this from an IDE terminal, the window may have appeared")
            print("[i] behind other windows or may not have worked correctly.")
            print()
            print("[i] You can still use the launcher with:")
            print("   - options.txt performance settings (PvP profile)")
            print("   - High Performance power plan")
            print("   - CPU priority boost")
            print("   - FPS counter overlay")
            print()
            print("[i] Engine-level mods (LeviOptimize, Beryllium) require a Microsoft")
            print("   account login.")
            print()
            try:
                response = input("[i] Continue without mods? (y/n) ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n[i] Setup cancelled")
                return False
            
            if response in ('y', 'yes'):
                print("[i] Continuing without Microsoft login...")
                return False
            else:
                print("[i] To log in later, run:")
                print(f"   & \"{exe}\" account login")
                return False


def _prompt_manual_login_gui(exe):
    """Prompt the user to sign in via the LeviLauncher GUI when CLI login fails.
    
    The GUI method is more reliable as it uses the built-in avatar sign-in flow
    instead of the Windows Account Manager command-line interface.
    
    Returns True if logged in after manual sign-in, False otherwise.
    """
    print("[i] You can sign in through the LeviLauncher GUI instead:")
    print()
    print("[i] 1. Double-click LeviLauncher.exe to open the launcher window")
    print("[i] 2. Click the avatar icon (person symbol) in the top-right corner")
    print("[i] 3. Sign in with your Microsoft account that owns Minecraft")
    print("[i] 4. Once signed in, close LeviLauncher and press Enter here")
    print()
    print(f"[i] LeviLauncher is located at: {exe}")
    print()
    
    try:
        response = input("[i] Press Enter after signing in (or type 'skip' to continue without mods)...").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n[i] Login cancelled")
        return False

    if response == "skip":
        print("[i] Skipping Microsoft login — engine-level mods will not be available.")
        print("[i] The launcher will still work with options.txt and OS optimizations.")
        return False

    # Give a moment for auth data to be written
    time.sleep(1)

    # Verify login was successful
    result = subprocess.run(
        [str(exe), "account", "status"],
        capture_output=True, text=True, check=False
    )
    if result.returncode == 0 and "Not signed in" not in result.stdout:
        print("[+] Microsoft account logged in successfully")
        return True
    else:
        print("[!] Login still not detected.")
        print()
        print("[i] You can still use the launcher with:")
        print("   - options.txt performance settings (PvP profile)")
        print("   - High Performance power plan")
        print("   - CPU priority boost")
        print("   - FPS counter overlay")
        print()
        print("[i] Engine-level mods (LeviOptimize, Beryllium) require a Microsoft")
        print("   account login.")
        print()
        try:
            response = input("[i] Continue without mods? (y/n) ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[i] Setup cancelled")
            return False
        
        if response in ('y', 'yes'):
            print("[i] Continuing without Microsoft login...")
            return False
        else:
            print("[i] To log in later, open LeviLauncher.exe and click the avatar icon.")
            return False


def install_bedrock_with_loader(exe):
    """Install the latest LeviLamina-supported Bedrock version.
    
    Queries for the latest supported version instead of using "latest",
    which may resolve to an unsupported version.
    Ensures Microsoft account is logged in before attempting install.
    If login is skipped, returns False but does not mark setup as failed.
    """
    # Ensure Microsoft account is logged in first
    logged_in = ensure_logged_in(exe)
    if not logged_in:
        print("[i] Skipping Bedrock with LeviLamina installation (requires Microsoft login)")
        print("[i] The launcher will still work with options.txt and OS optimizations")
        return False
    
    version = get_latest_supported_version(exe)
    if version:
        print(f"[i] latest LeviLamina-supported version: {version}")
        result = cli(exe, "install", version, "--loader", "--use")
    else:
        print("[!] Could not determine supported version, trying 'latest'...")
        result = cli(exe, "install", "latest", "--loader", "--use")
    
    if result and result.returncode == 0:
        print("[+] Bedrock with LeviLamina installed")
        return True
    
    # If auth interaction is still required, remind the user
    if result and result.returncode != 0:
        stderr = getattr(result, 'stderr', '') or ''
        if 'ERR_AUTH_INTERACTION_REQUIRED' in stderr or 'account login' in stderr:
            print("[!] Still need to sign in. Please run manually:")
            print(f"   {exe} account login")
            print(f"   Then retry: {exe} install {version or 'latest'} --loader --use")
    return False


def play(exe):
    """Launch the game via LeviLauncher.
    
    Command: LeviLauncher.exe play
    """
    return cli(exe, "play", capture=False)


def mod_install(exe, mod_url):
    """Install a mod via LeviLauncher CLI.
    
    Command: LeviLauncher.exe mod install <url>
    """
    result = cli(exe, "mod", "install", mod_url)
    if result and result.returncode == 0:
        print(f"[+] Mod installed: {mod_url}")
        return True
    return False
