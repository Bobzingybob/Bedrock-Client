#!/usr/bin/env python3
"""
bedrock_boost_win.py - Bedrock Boost Launcher

Comprehensive Bedrock optimization launcher that wraps LeviLauncher and automates
the installation and management of performance mods (LeviOptimize, Beryllium) while
applying Competitive PvP-optimized settings.

Does NOT touch game memory or modify the client. It only:
  1. edits options.txt with performance profiles (with backup)
  2. switches Windows to the High performance power plan while you play
  3. launches via LeviLauncher (or fallback to Microsoft Store)
  4. raises the game's CPU priority
  5. shows a click-through FPS counter (PresentMon)
  6. restores your power plan when the game closes

Setup:
  pip install psutil
  Download PresentMon-x.x.x-x64.exe from
  https://github.com/GameTechDev/PresentMon/releases and put it in the
  same folder as this script.

Usage (run from an ADMIN terminal for the FPS counter + priority boost):
  python bedrock_boost_win.py [--profile pvp] [--no-overlay] [--dry-run]
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
from profiles.pvp import PvPProfile


# ---------------------------------------------------------------- profiles
PROFILES = {
    "pvp": PvPProfile(),
}


# ---------------------------------------------------------------- setup wizard
def run_setup():
    """Run the first-time setup wizard."""
    from setup.levilauncher import find_levilauncher, install_levilauncher, install_bedrock_with_loader
    from setup.levilamina import install_all as install_levilamina_mods
    from setup.beryllium import install_all as install_beryllium
    
    print("=" * 60)
    print("Bedrock Boost Launcher - First-Time Setup")
    print("=" * 60)
    
    # Step 1: LeviLauncher
    print("\n[1/3] Checking LeviLauncher...")
    ll_exe = find_levilauncher()
    if ll_exe:
        print(f"[+] LeviLauncher found: {ll_exe}")
    else:
        print("[i] LeviLauncher not found. Would you like to install it? (y/n)")
        try:
            if input().strip().lower() == 'y':
                ll_exe = install_levilauncher()
                if not ll_exe:
                    print("[!] LeviLauncher installation failed")
                    return False
            else:
                print("[i] Skipping LeviLauncher installation")
        except (EOFError, KeyboardInterrupt):
            print("\n[i] Setup cancelled")
            return False
    
    # Step 2: Bedrock with LeviLamina
    if ll_exe:
        print("\n[2/3] Checking Bedrock with LeviLamina...")
        print("[i] Installing latest Bedrock with LeviLamina loader...")
        if not install_bedrock_with_loader(ll_exe):
            print("[!] Bedrock installation failed")
            return False
    
    # Step 3: LeviOptimize
    if ll_exe:
        print("\n[3/3] Installing LeviOptimize...")
        if not install_levilamina_mods(ll_exe):
            print("[!] LeviOptimize installation failed")
            return False
    
    # Step 4: Beryllium
    print("\n[Bonus] Installing Beryllium...")
    if not install_beryllium():
        print("[!] Beryllium installation failed")
        print("[i] You can install it manually from CurseForge")
    
    print("\n" + "=" * 60)
    print("Setup complete! You can now launch the game with optimizations.")
    print("=" * 60)
    return True


# ---------------------------------------------------------------- desktop shortcut
def make_shortcut():
    """Create a desktop shortcut that runs as admin."""
    script = str(Path(__file__).resolve())
    python = sys.executable
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
    print(f"[+] shortcut created: {lnk}  (runs as admin, PvP profile)")


# ---------------------------------------------------------------- launch sequence
def launch_game(profile, dry_run=False, no_overlay=False):
    """Execute the full launch sequence with all optimizations."""
    from setup.levilauncher import find_levilauncher, play as play_via_levilauncher
    from utils.os_optimizations import apply_all_os_optimizations, restore_os_optimizations
    
    # Pre-launch: apply options.txt profile
    profile_obj = PROFILES.get(profile)
    if profile_obj:
        options = profile_obj.get_options()
    else:
        options = {}
    
    apply_options(options, dry_run)
    
    # Find PresentMon
    pm_exe = None
    if not no_overlay:
        matches = sorted(glob.glob(str(SCRIPT_DIR / "PresentMon*.exe")))
        pm_exe = matches[-1] if matches else None
        if not pm_exe:
            print("[i] FPS counter off: put PresentMon-x.x.x-x64.exe next to this script "
                  "(github.com/GameTechDev/PresentMon/releases)")
        elif not ctypes.windll.shell32.IsUserAnAdmin():
            print("[i] not running as admin - FPS counter may fail to see the game")
    
    if dry_run:
        print(f"[dry-run] would switch to High performance plan, launch game, "
              f"and {'show' if pm_exe else 'skip'} the FPS counter")
        return
    
    # Pre-launch: power plan
    previous_plan = set_high_performance()
    
    # Pre-launch: OS optimizations (Xbox Game Bar, graphics settings)
    os_states = apply_all_os_optimizations()
    
    # Launch via LeviLauncher or fallback
    ll_exe = find_levilauncher()
    if ll_exe:
        print(f"[i] launching via LeviLauncher: {ll_exe}")
        play_via_levilauncher(ll_exe)
    else:
        print("[i] LeviLauncher not found, launching via Microsoft Store...")
        os.startfile("minecraft:")
    
    print("[i] launching...")
    
    # Wait for game process
    game = wait_for_game()
    if not game:
        print("[!] game process not found within 90s")
        return
    
    # Post-launch: CPU priority
    set_high_priority(game)
    
    # FPS overlay
    monitor = None
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
        game.wait()
    finally:
        # Cleanup
        if monitor:
            monitor.stop()
        if previous_plan:
            restore_power_plan(previous_plan)
        restore_os_optimizations(os_states)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="Bedrock Boost Launcher - Competitive PvP optimization"
    )
    ap.add_argument("--profile", choices=list(PROFILES.keys()), default="pvp",
                    help="Optimization profile to apply (default: pvp)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be done without making changes")
    ap.add_argument("--no-overlay", action="store_true",
                    help="Disable FPS overlay")
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
    
    launch_game(args.profile, args.dry_run, args.no_overlay)


if __name__ == "__main__":
    main()
