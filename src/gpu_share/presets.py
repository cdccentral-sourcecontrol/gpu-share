"""Resolution presets for NVENC encoding."""

DEFAULT_PRESETS = {
    "1920x1080": {
        "vf": "scale=1920:-2,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
        "level": "4.0",
        "maxrate": "6000k",
        "bufsize": "6000k",
        "profile": "baseline",
        "preset": "p5",
        "cq": 22,
        "fps": 25,
    },
    "1280x720": {
        "vf": "scale=1280:-2,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
        "level": "3.1",
        "maxrate": "3000k",
        "bufsize": "3000k",
        "profile": "baseline",
        "preset": "p5",
        "cq": 22,
        "fps": 25,
    },
}

# Required keys for a valid preset
_REQUIRED = {"vf", "level", "maxrate", "bufsize"}


def load_presets(custom_presets=None):
    """Merge custom presets with defaults. Custom overrides defaults."""
    presets = dict(DEFAULT_PRESETS)
    if custom_presets:
        for name, vals in custom_presets.items():
            if not _REQUIRED.issubset(vals.keys()):
                missing = _REQUIRED - vals.keys()
                raise ValueError(f"Preset '{name}' missing required keys: {missing}")
            merged = dict(DEFAULT_PRESETS.get(name, DEFAULT_PRESETS["1920x1080"]))
            merged.update(vals)
            presets[name] = merged
    return presets
