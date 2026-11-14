"""Beryllium addon installation guidance.

Beryllium is a rendering optimization texture pack for Bedrock that provides:
- V-Sync unlock (zero latency)
- Smart entity culling
- Shadow stripping
- Optimized leaves and grass

Since Beryllium is a mobile-focused pack not easily automatable via CurseForge API
(Cloudflare protection, no LeviLauncher CurseForge index entry), this module provides
clear manual installation instructions instead.
"""


def find_beryllium():
    """Check if Beryllium might already be installed by checking for the .mcpack file.
    
    Returns True if a Beryllium pack file is found.
    """
    import os
    from pathlib import Path
    
    search_paths = [
        Path(os.environ.get("APPDATA", "")) / "Minecraft Bedrock",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Packages" / "Microsoft.MinecraftUWP_8wekyb3d8bbwe" / "LocalState",
    ]
    
    for base in search_paths:
        if base.exists():
            for pack_type in ("resource_packs", "behavior_packs"):
                for found_dir in base.glob(f"**/{pack_type}"):
                    if found_dir.exists():
                        for item in found_dir.iterdir():
                            if "beryllium" in item.name.lower():
                                return True
    return False


def install_all():
    """Guide the user through manual Beryllium installation.
    
    Returns True (always succeeds since it's just instructions).
    """
    if find_beryllium():
        print("[+] Beryllium already installed")
        return True
    
    print("[i] Beryllium is a rendering optimization pack (V-Sync unlock, entity culling, shadow stripping)")
    print("[i] It must be installed manually since CurseForge blocks automated downloads.")
    print()
    print("[i] To install Beryllium:")
    print("   1. Download from: https://www.curseforge.com/minecraft-bedrock/texture-packs/beryllium")
    print("   2. Click the green 'Download File' button")
    print("   3. Open the downloaded .mcpack file (it will auto-import into Minecraft)")
    print("   4. In Minecraft: Settings > Video > Global Resources > My Packs > Enable Beryllium")
    print()
    print("[i] Alternatively, use LeviLauncher after setting up your instance:")
    print("   LeviLauncher.exe pack import <path-to-beryllium.mcpack>")
    print()
    print("[+] Beryllium setup guidance complete (manual installation required)")
    return True
