# 0013 — plugin_system (Bonus)

## Summary

A lightweight plugin architecture allowing contributors to add custom scoring modes, visualizations, input methods, and practice routines without modifying core code.

## Module

`src/keyfall/plugins/` (new package)

## Public API

```python
# Plugin base classes
class ScoringPlugin(Protocol):
    name: str
    def on_hit(self, result: HitResult) -> int: ...
    def on_frame(self, dt: float) -> None: ...
    def get_score(self) -> int: ...

class ViewPlugin(Protocol):
    """A full-screen view contributed by a plugin. See 0015_ui_views_architecture."""
    name: str
    display_name: str
    def on_enter(self, context: ViewContext) -> None: ...
    def on_exit(self) -> None: ...
    def handle_event(self, event: pygame.event.Event) -> ViewAction | None: ...
    def update(self, dt: float) -> ViewAction | None: ...
    def draw(self, surface: pygame.Surface) -> None: ...

class PanelPlugin(Protocol):
    """A panel overlay injected into an existing view. See 0015_ui_views_architecture."""
    name: str
    target_view: str
    anchor: Literal["top", "bottom", "left", "right", "overlay"]
    size: int
    def layout(self, rect: pygame.Rect) -> None: ...
    def handle_event(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: pygame.Surface) -> None: ...

class VisualizationPlugin(Protocol):
    """A lightweight render-only overlay (e.g. particles). For full views, use ViewPlugin."""
    name: str
    def render(self, surface: pygame.Surface, song: Song, position: float) -> None: ...

class InputPlugin(Protocol):
    name: str
    def poll(self) -> LiveNoteEvent | None: ...
    def close(self) -> None: ...

# Plugin manager
class PluginManager:
    def discover(self) -> None: ...
    def register(self, plugin: Any) -> None: ...
    def get_scoring_plugins(self) -> list[ScoringPlugin]: ...
    def get_view_plugins(self) -> list[type[ViewPlugin]]: ...
    def get_panel_plugins(self) -> list[type[PanelPlugin]]: ...
    def get_visualization_plugins(self) -> list[VisualizationPlugin]: ...
    def get_input_plugins(self) -> list[InputPlugin]: ...
```

## Detailed Design

### Discovery

Use Python's `importlib.metadata` entry points:

```toml
# In a plugin's pyproject.toml:
[project.entry-points."keyfall.plugins"]
my_scoring = "my_plugin:MyScoringPlugin"

[project.entry-points."keyfall.views"]
my_view = "my_plugin.views:MyCustomView"

[project.entry-points."keyfall.panels"]
my_panel = "my_plugin.panels:MyOverlayPanel"
```

The `PluginManager.discover()` method scans entry points at startup:

```python
from importlib.metadata import entry_points

def discover(self) -> None:
    eps = entry_points(group="keyfall.plugins")
    for ep in eps:
        plugin_cls = ep.load()
        self.register(plugin_cls())
```

### Plugin Categories

**Scoring Plugins** — alternative scoring systems:
- Combo multiplier mode (DDR-style)
- Accuracy-only mode (no points, just percentage)
- Time attack (race against the clock)

**View Plugins** — entirely new full-screen views:
- Rhythm game mode (DDR-style lane hits)
- Sight-reading drill view
- Two-player split-screen
- See `0015_ui_views_architecture.md` for the `View` protocol.

**Panel Plugins** — UI panels injected into existing views:
- Combo counter overlay
- Particle effects layer
- Chord chart sidebar
- See `0015_ui_views_architecture.md` for the `PanelPlugin` protocol.

**Visualization Plugins** — lightweight render-only overlays:
- Guitar Hero-style highway
- Circular / radial note display
- Color themes

**Input Plugins** — alternative input sources:
- OSC input (from other apps)
- Audio pitch detection (microphone → pitch → MIDI)
- Gamepad / dance pad mapping

### Plugin Lifecycle

```
discover() → instantiate → register()
  ↓
Game loop:
  plugin.on_frame(dt)        # scoring
  plugin.render(surface, …)  # visualization
  plugin.poll()              # input
  ↓
Shutdown:
  plugin.close()             # cleanup
```

### Configuration

Plugins can expose settings via a simple dict:

```python
class MyPlugin:
    @staticmethod
    def get_settings_schema() -> dict:
        return {
            "multiplier_cap": {"type": "int", "default": 8, "min": 1, "max": 16},
        }
```

The settings UI renders these automatically.

### Built-in Plugins

Ship these as examples and defaults:
1. `StandardScoring` — the default PERFECT/GOOD/OK/MISS scoring.
2. `WaterfallVisualization` — the default falling-note view.
3. `MidiInputPlugin` — wraps `MidiInput`.

### Security

- Plugins run in the same process (no sandboxing for v1).
- Only load entry points from explicitly installed packages.
- Document that users install plugins at their own risk.

## Testing Plan

| Test | Assertion |
|------|-----------|
| discover() finds installed plugins | plugin list non-empty with test plugin |
| register() adds to correct category | scoring plugin in scoring list |
| ScoringPlugin protocol enforced | missing method raises TypeError |
| Plugin on_hit called during evaluation | mock plugin receives call |
| Plugin render called during draw | mock plugin receives surface |

## Dependencies

- `importlib.metadata` (stdlib)
- `typing.Protocol` (stdlib)

## Open Questions

- Should plugins be able to modify the game loop order (priority system)?
- Should we support hot-reloading plugins during development?
