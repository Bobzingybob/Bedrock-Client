"""Competitive PvP optimization profile."""
from profiles.base import BaseProfile


class PvPProfile(BaseProfile):
    """Maximum responsiveness for competitive PvP play.
    
    - VSync off, unlimited FPS
    - Minimal render distance (8 chunks)
    - Simulation distance reduced (6 chunks)
    - Fancy graphics off, bobbing off
    - Smooth lighting off
    - Animated textures off
    """
    
    name = "pvp"
    description = "Competitive PvP: maximum responsiveness"
    
    options = {
        "gfx_vsync": "0",
        "gfx_max_framerate": "0",
        "gfx_viewdistance": "8",
        "gfx_fancygraphics": "0",
        "gfx_viewbobbing": "0",
        "gfx_ao": "0",
        "gfx_animatetextures": "0",
        "world_simulationdistance": "6",
    }
