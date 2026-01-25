---
name: Sound Design
description: Guidelines and workflows for creating retro-style game audio.
---

# Sound Design Skill

This skill defines the standards and processes for creating sound effects and music for the Starcrash project.

## Aesthetic Goals
- **Style**: Retro, 8-bit/16-bit era.
- **Feel**: Crunchy, distinct, arcade-like.
- **Inspiration**: Atari 2600, NES, Commodore 64.

## Technical Standards
- **Format**: WAV for source, OGG for distribution if needed.
- **Sample Rate**: 44.1kHz (or downsampled to 22kHz/11kHz for effect).
- **Bit Depth**: 16-bit.
- **Channels**: Mono for SFX, Stereo for Music.

## Naming Convention
- `[type]_[description]_[variant].wav`
- Examples:
    - `sfx_laser_fast.wav`
    - `sfx_explosion_subtle.wav`
    - `ui_select_click.wav`

## Tools
### Starcrash Asset MCP
Use the `mcp_starcrash-assets_generate_sfx` tool to procedurally generate placeholder and production-ready retro sounds.

#### Usage
```python
# Generate a laser sound
generate_sfx(name="sfx_laser_01", type="laser")

# Generate an explosion
generate_sfx(name="sfx_explosion_boss", type="explosion")
```

#### Types
- `laser`: Pew-pew sounds, frequency sweeps down.
- `explosion`: White noise bursts with decay.
- `powerup`: Positive chimes, frequency sweeps up.

## Integration
- Place all generated assets in `d:/Development/starcrash/game/assets/sfx/` (or the configured output directory of the MCP).
- Register sounds in the Godot AudioBusLayout if necessary.
