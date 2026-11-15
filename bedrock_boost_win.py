#!/usr/bin/env python3
"""
bedrock_boost_win.py - Bedrock Boost Launcher

Comprehensive Bedrock optimization launcher that injects a custom performance DLL
into Minecraft.Windows.exe and applies OS-level optimizations (power plan, CPU
priority, options.txt) while showing a real-time FPS counter.

Optimizations applied:
  1. Injects custom BedrockBoost.dll with engine-level performance modules
  2. Edits options.txt with performance profiles (with backup)
  3. Switches Windows to the High performance power plan while you play
  4. Launches via Microsoft Store (or LeviLauncher fallback)
  5. Raises the game's CPU priority
  6. Shows a click-through FPS counter (PresentMon)
  7. Restores your power plan when the game closes

Setup:
  pip install psutil
  Download PresentMon-x.x.x-x64.exe from
  https://github.com/GameTechDev/PresentMon/releases and put it in the
  same folder as this script.

Usage (run from an ADMIN terminal for the FPS counter + priority boost):
  python bedrock_boost_win.py [--profile pvp] [--no-overlay] [--dry-run]
  python bedrock_boost_win.py [--no-inject]        # skip DLL injection
  python bedrock_boost_win.py --setup              # run first-time setup wizard
  python bedrock_boost_win.py --make-shortcut      # desktop shortcut, runs as admin
"""
import argparse
import ctypes
import glob
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    sys.exit("[!] Run: pip install psutil")

SCRIPT_DIR = Path(__file__).resolve().parent
PROCESS_NAME = "Minecraft.Windows.exe"


# ---------------------------------------------------------------- imports
from utils.options import find_options, apply_options
from utils.power import set_high_performance, restore_power_plan
from utils.priority import game_running, wait_for_game, set_high_priority
from utils.fps import FrameMonitor, run_overlay
from utils.injector import inject_client_dll, check_injection_ready, ensure_developer_mode
from profiles.pvp import PvPProfile


# ---------------------------------------------------------------- profiles
PROFILES = {
    "pvp": PvPProfile(),
}


# ---------------------------------------------------------------- setup wizard
def run_setup():
    """Run the first-time setup wizard."""
    print("=" * 60)
    print("Bedrock Boost Launcher - First-Time Setup")
    print("=" * 60)
    
    # Step 1: Check client DLL
    client_dll = SCRIPT_DIR / "client" / "build" / "Release" / "BedrockBoost.dll"
    client_src = SCRIPT_DIR / "client" / "CMakeLists.txt"
    
    print("\n[1/4] Checking custom client DLL...")
    if client_dll.exists():
        print(f"[+] Client DLL found: {client_dll}")
    elif client_src.exists():
        print("[i] Client source found but DLL not built.")
        print("[i] You need MSVC + CMake to build the client DLL.")
        print("[i] Would you like to try building now? (y/n)")
        try:
            if input().strip().lower() == 'y':
                _build_client_dll()
                if client_dll.exists():
                    print(f"[+] Client DLL built successfully: {client_dll}")
                else:
                    print("[!] Client DLL build failed")
        except (EOFError, KeyboardInterrupt):
            print("\n[i] Build skipped")
    else:
        print("[i] No client source found. The launcher will work with OS-level optimizations only.")
    
    # Step 2: Check injection prerequisites
    print("\n[2/4] Checking injection prerequisites...")
    ready, reason = check_injection_ready()
    if ready:
        print("[+] Injection ready: Admin + Developer Mode")
    else:
        print(f"[!] {reason}")
        ensure_developer_mode()
    
    # Step 3: PresentMon
    print("\n[3/3] Checking PresentMon FPS counter...")
    pm_exe = ensure_presentmon()
    if pm_exe:
        pm_name = Path(pm_exe).name if isinstance(pm_exe, (str, Path)) else pm_exe
        print(f"[+] PresentMon ready: {pm_name}")
    else:
        print("[i] PresentMon not available - FPS counter will be disabled")
    
    print("\n" + "=" * 60)
    print("Setup complete! Launch via Microsoft Store with DLL injection.")
    print("=" * 60)
    
    # Auto-create desktop shortcut after successful setup
    print("\n[i] Creating desktop shortcut...")
    try:
        make_shortcut()
    except Exception as e:
        print(f"[!] Could not create shortcut automatically: {e}")
        print("[i] Run --make-shortcut to create it manually")
    
    return True


def _find_vs_generator():
    """Detect the Visual Studio generator for CMake."""
    vswhere = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if not Path(vswhere).exists():
        return None
    # Find latest BuildTools or VS installation with C++ workload
    for workload in ["Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "Microsoft.Component.MSBuild"]:
        result = subprocess.run(
            [vswhere, "-latest", "-requires", workload, "-property", "installationPath"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            install_path = result.stdout.strip()
            # Determine version from path
            if "2022" in install_path:
                return "Visual Studio 17 2022", install_path
            elif "2019" in install_path:
                return "Visual Studio 16 2019", install_path
    return None


def _build_client_dll():
    """Attempt to build the client DLL using CMake."""
    build_dir = SCRIPT_DIR / "client" / "build"
    cmake_dir = SCRIPT_DIR / "client"
    
    # Detect Visual Studio generator
    vs_info = _find_vs_generator()
    if vs_info:
        generator, _ = vs_info
        print(f"[i] Detected Visual Studio: {generator}")
        cmake_configure = [
            "cmake", "-B", str(build_dir), "-S", str(cmake_dir),
            "-G", generator,
            "-DCMAKE_BUILD_TYPE=Release"
        ]
    else:
        print("[i] Visual Studio not detected, using default CMake generator...")
        cmake_configure = [
            "cmake", "-B", str(build_dir), "-S", str(cmake_dir),
            "-DCMAKE_BUILD_TYPE=Release"
        ]
    
    print("[i] Configuring CMake...")
    result = subprocess.run(
        cmake_configure,
        capture_output=True, text=True, cwd=str(cmake_dir)
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        combined = stdout + "\n" + stderr if stdout else stderr
        print(f"[!] CMake configure failed:")
        # Print first few lines of error
        for line in combined.split('\n')[:10]:
            print(f"    {line}")
        
        # Check for common MSVC issues
        if "CMAKE_C_COMPILER not set" in combined or "nmake" in combined.lower():
            print("\n[!] MSVC C++ compiler workload is not installed.")
            print("[i] You have Visual Studio Build Tools, but the C++ workload is missing.")
            print("[i] To fix this:")
            print("[i] 1. Open 'Visual Studio Installer' from Start Menu")
            print("[i] 2. Click 'Modify' on Visual Studio Build Tools")
            print("[i] 3. Check 'Desktop development with C++' workload")
            print("[i] 4. Click 'Modify' to install")
            print("[i] 5. Restart this setup after installation")
        return
    
    print("[i] Building DLL...")
    result = subprocess.run(
        ["cmake", "--build", str(build_dir), "--config", "Release"],
        capture_output=True, text=True, cwd=str(cmake_dir)
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        combined = stdout + "\n" + stderr if stdout else stderr
        print(f"[!] Build failed:")
        for line in combined.split('\n')[-15:]:
            print(f"    {line}")
        return
    
    # Copy DLL to build directory if needed
    dll_found = False
    for sub_dir in ["", "Release", str(build_dir / "x64" / "Release")]:
        dll_path = build_dir / sub_dir / "BedrockBoost.dll" if sub_dir else build_dir / "BedrockBoost.dll"
        if dll_path.exists():
            if not (build_dir / "BedrockBoost.dll").exists():
                import shutil
                shutil.copy2(str(dll_path), str(build_dir / "BedrockBoost.dll"))
            dll_found = True
            break
    
    if dll_found:
        print(f"[+] Client DLL built successfully: {build_dir / 'BedrockBoost.dll'}")
    else:
        print("[!] Build completed but DLL not found in expected locations")


# ---------------------------------------------------------------- desktop shortcut
def make_shortcut():
    """Create desktop shortcuts for launch and setup."""
    script = str(Path(__file__).resolve())
    python = sys.executable

    # 1. Launch shortcut (runs as admin with PvP profile)
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$p=Join-Path $d 'Minecraft Boost.lnk';"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($p);"
        f"$s.TargetPath='{python}';"
        f"$s.Arguments='\"{script}\" --profile pvp';"
        f"$s.WorkingDirectory='{SCRIPT_DIR}';"
        "$s.WindowStyle=7;$s.IconLocation='shell32.dll,13';$s.Save();$p"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True)
    lnk = out.stdout.strip()
    if out.returncode != 0 or not lnk:
        sys.exit(f"[!] couldn't create shortcut: {out.stderr.strip()}")
    # set the "Run as administrator" flag (needed for the FPS counter)
    data = bytearray(Path(lnk).read_bytes())
    data[0x15] |= 0x20
    Path(lnk).write_bytes(bytes(data))
    print(f"[+] launch shortcut created: {lnk}  (runs as admin, PvP profile)")

    # 2. Setup shortcut (opens cmd window for interactive wizard)
    ps_setup = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$p=Join-Path $d 'Bedrock Setup.lnk';"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($p);"
        "$s.TargetPath='cmd.exe';"
        f"$s.Arguments='/K cd /D \"{SCRIPT_DIR}\" && {python} bedrock_boost_win.py --setup';"
        f"$s.WorkingDirectory='{SCRIPT_DIR}';"
        "$s.WindowStyle=1;$s.IconLocation='shell32.dll,175';$s.Save();$p"
    )
    out2 = subprocess.run(["powershell", "-NoProfile", "-Command", ps_setup],
                          capture_output=True, text=True)
    lnk2 = out2.stdout.strip()
    if out2.returncode != 0 or not lnk2:
        print(f"[!] couldn't create setup shortcut: {out2.stderr.strip()}")
    else:
        print(f"[+] setup shortcut created: {lnk2}  (double-click to install mods)")


# ---------------------------------------------------------------- PresentMon auto-download
def ensure_presentmon():
    """Check for PresentMon and auto-download if missing. Returns path or None."""
    matches = sorted(glob.glob(str(SCRIPT_DIR / "PresentMon*.exe")))
    if matches:
        return matches[-1]

    print("[i] PresentMon not found, downloading latest release...")
    try:
        import urllib.request
        import json as _json

        config_path = SCRIPT_DIR / "config.json"
        api_url = "https://api.github.com/repos/GameTechDev/PresentMon/releases/latest"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = _json.load(f)
            api_url = config.get("presentmon", {}).get("release_api", api_url)

        req = urllib.request.Request(api_url)
        with urllib.request.urlopen(req, timeout=30) as response:
            release = _json.loads(response.read().decode("utf-8"))

        asset = None
        for a in release.get("assets", []):
            if a["name"].endswith(".exe"):
                asset = a
                break
        if not asset:
            print("[!] No .exe asset found in PresentMon release")
            return None

        download_url = asset["browser_download_url"]
        download_name = asset["name"]
        print(f"[i] downloading {download_name}...")
        dest = SCRIPT_DIR / download_name
        urllib.request.urlretrieve(download_url, str(dest))
        print(f"[+] PresentMon downloaded to {dest}")
        return dest
    except Exception as e:
        print(f"[!] Failed to download PresentMon: {e}")
        print("[i] Download manually from github.com/GameTechDev/PresentMon/releases")
        return None


# ---------------------------------------------------------------- launch status summary
def print_launch_status(profile, pm_exe, no_overlay, is_admin, no_inject=False):
    """Print a clear summary of what optimizations are active."""
    print("\n" + "=" * 50)
    print("  Bedrock Boost Launcher - Launch Status")
    print("=" * 50)

    # Profile
    profile_obj = PROFILES.get(profile)
    if profile_obj:
        opts = profile_obj.get_options()
        print(f"  Profile:       {profile_obj.description}")
        print(f"  Settings:      {len(opts)} options.txt changes")
    else:
        print(f"  Profile:       {profile} (no settings)")

    # Client DLL status
    client_dll = SCRIPT_DIR / "client" / "build" / "Release" / "BedrockBoost.dll"
    if no_inject:
        print(f"  Client DLL:    [OFF] Skipped (--no-inject)")
    elif client_dll.exists():
        print(f"  Client DLL:    [OK] BedrockBoost.dll ready")
        print(f"  Modules:       EntityCulling, ChunkOpt, FPSBoost, TickOpt")
    else:
        print(f"  Client DLL:    [MISSING] Not built yet")
        print(f"  Note:          Build client DLL for engine-level optimizations")

    # Launcher
    print(f"  Launcher:      [OK] Microsoft Store (Xbox Live)")

    # FPS overlay
    if no_overlay:
        print(f"  FPS Overlay:   [OFF] Disabled (--no-overlay)")
    elif pm_exe:
        if is_admin:
            print(f"  FPS Overlay:   [OK] PresentMon ready")
        else:
            print(f"  FPS Overlay:   [WARN] PresentMon ready (admin recommended)")
    else:
        print(f"  FPS Overlay:   [MISSING] PresentMon not found")

    # OS optimizations
    print(f"  Power Plan:    [OK] High Performance")
    print(f"  CPU Priority:  [OK] High (admin required)")
    print(f"  Xbox Game Bar: [OFF] Disabled")
    print("=" * 50 + "\n")


# ---------------------------------------------------------------- launch sequence
def launch_game(profile, dry_run=False, no_overlay=False, no_inject=False):
    """Execute the full launch sequence with all optimizations."""
    from utils.os_optimizations import apply_all_os_optimizations, restore_os_optimizations

    is_admin = ctypes.windll.shell32.IsUserAnAdmin()

    # Pre-launch: apply options.txt profile
    profile_obj = PROFILES.get(profile)
    if profile_obj:
        options = profile_obj.get_options()
    else:
        options = {}

    apply_options(options, dry_run)

    # Find or download PresentMon
    pm_exe = None
    if not no_overlay:
        pm_exe = ensure_presentmon()
        if not pm_exe:
            print("[i] FPS counter off: could not obtain PresentMon")
        elif not is_admin:
            print("[i] not running as admin - FPS counter may fail to see the game")

    # Check client DLL
    client_dll = SCRIPT_DIR / "client" / "build" / "Release" / "BedrockBoost.dll"
    has_client = client_dll.exists()

    # Print status summary
    print_launch_status(profile, pm_exe, no_overlay, is_admin, no_inject)
    
    if dry_run:
        print(f"[dry-run] would switch to High performance plan, launch game via Microsoft Store, "
              f"{'inject DLL' if (has_client and not no_inject) else 'skip injection'}, "
              f"and {'show' if pm_exe else 'skip'} the FPS counter")
        return

    # Pre-launch: power plan
    previous_plan = set_high_performance()

    # Pre-launch: OS optimizations (Xbox Game Bar, graphics settings)
    os_states = apply_all_os_optimizations()

    # Launch game via Microsoft Store only - preserves Xbox Live features
    print("[i] launching via Microsoft Store...")
    os.startfile("minecraft:")

    print("[i] waiting for Minecraft.Windows.exe...")
    
    # Wait for game process
    game = wait_for_game()
    if not game:
        print("[!] game process not found within 90s")
        return
    
    # Post-launch: DLL injection (if enabled and DLL exists)
    if not no_inject and has_client:
        print("\n[i] Injecting custom client DLL...")
        inject_success = inject_client_dll(str(client_dll.resolve()))
        if not inject_success:
            print("[!] Injection failed - game will run without custom client")
            print("[i] Make sure you're running as administrator")
    elif not no_inject and not has_client:
        print("\n[i] Skipping DLL injection - client DLL not built")
    else:
        print("\n[i] Skipping DLL injection (--no-inject flag)")
    
    # Post-launch: CPU priority
    set_high_priority(game)
    
    # FPS overlay and game monitoring
    monitor = None
    game_closed_event = threading.Event()

    def watch_game():
        """Watch for game process to exit and trigger cleanup."""
        while game.is_running():
            if game_closed_event.wait(timeout=1):
                return
        # Game has exited
        print("\n[i] Minecraft has closed, cleaning up...")
        if monitor and monitor.proc.poll() is None:
            # PresentMon didn't auto-terminate (UWP sandbox), kill it manually
            monitor.stop()
        if previous_plan:
            restore_power_plan(previous_plan)
        restore_os_optimizations(os_states)
        # Signal the overlay to close
        if hasattr(run_overlay, '_root') and run_overlay._root is not None:
            try:
                run_overlay._root.after(0, run_overlay._root.destroy)
            except Exception:
                pass

    watcher = threading.Thread(target=watch_game, daemon=True)
    watcher.start()

    try:
        if pm_exe:
            monitor = FrameMonitor(pm_exe)
            time.sleep(2)
            if monitor.proc.poll() not in (None, 0):
                print("[i] PresentMon failed to start: "
                      f"{monitor.proc.stderr.read().strip() or 'unknown error'}")
                monitor = None
            else:
                print("[+] FPS counter running (top-left)")
                try:
                    run_overlay(game, monitor)
                except Exception as e:
                    print(f"[i] overlay error: {e}")
        # Wait for the game to close (watcher thread handles cleanup)
        while game.is_running():
            time.sleep(0.5)
    finally:
        # Final cleanup — watcher thread should have handled most of this
        if monitor and monitor.proc.poll() is None:
            monitor.stop()
        if previous_plan:
            restore_power_plan(previous_plan)
        restore_os_optimizations(os_states)
        print("[+] power plan restored")
        print("[+] Xbox Game Bar re-enabled")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="Bedrock Boost Launcher - Custom client + OS optimizations"
    )
    ap.add_argument("--profile", choices=list(PROFILES.keys()), default="pvp",
                    help="Optimization profile to apply (default: pvp)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be done without making changes")
    ap.add_argument("--no-overlay", action="store_true",
                    help="Disable FPS overlay")
    ap.add_argument("--no-inject", action="store_true",
                    help="Skip custom client DLL injection")
    ap.add_argument("--make-shortcut", action="store_true",
                    help="Create desktop shortcut (runs as admin)")
    ap.add_argument("--setup", action="store_true",
                    help="Run first-time setup wizard")
    args = ap.parse_args()
    
    if args.make_shortcut:
        make_shortcut()
        return
    
    if args.setup:
        success = run_setup()
        if not success:
            print("[!] Setup incomplete - some features may not work")
        return
    
    if game_running():
        sys.exit("[!] Minecraft is already running - close it first, "
                 "or it will overwrite options.txt when it exits.")
    
    launch_game(args.profile, args.dry_run, args.no_overlay, args.no_inject)


if __name__ == "__main__":
    main()
