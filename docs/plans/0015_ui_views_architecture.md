# 0015 — UI Views Architecture

## Summary

Define a `View` protocol that governs all full-screen game states — three built-in views (Classic Waterfall, Practice Mode, Free Play) plus an extensible registration system so plugins can contribute entirely new views.

## Modules

- `src/keyfall/views/base.py` — `View` protocol and `ViewManager`
- `src/keyfall/views/waterfall_view.py` — Classic Waterfall
- `src/keyfall/views/practice_view.py` — Practice Mode
- `src/keyfall/views/freeplay_view.py` — Free Play / Sandbox
- `src/keyfall/views/menu_view.py` — Main menu and song picker
- `src/keyfall/views/__init__.py` — re-exports, built-in view registry
- Touches: `app.py`, `plugins/`, `config.py`

---

## View Protocol

Every view — built-in or plugin-provided — implements the same protocol:

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
import pygame

@runtime_checkable
class View(Protocol):
    """A full-screen game state (menu, gameplay, sandbox, etc.)."""

    name: str
    """Unique identifier used in navigation and plugin registration."""

    display_name: str
    """Human-readable label shown in menus."""

    @property
    def icon(self) -> str:
        """Optional icon/emoji for menu display."""
        ...

    def on_enter(self, context: ViewContext) -> None:
        """Called when this view becomes the active view.

        Use this for resource allocation, state reset, or
        starting audio/MIDI streams relevant to the view.
        """
        ...

    def on_exit(self) -> None:
        """Called when leaving this view.

        Clean up resources, stop audio, flush state.
        """
        ...

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        """Process a single pygame event.

        Return a ViewAction to trigger navigation (push, pop, switch),
        or None to continue in the current view.
        """
        ...

    def update(self, dt: float) -> ViewAction | None:
        """Per-frame logic update.

        dt: seconds since last frame.
        Return a ViewAction to navigate, or None.
        """
        ...

    def draw(self, surface: pygame.Surface) -> None:
        """Render the entire view to the given surface."""
        ...
```

### ViewContext

Shared state bag passed to views on entry. Avoids tight coupling between views and global singletons.

```python
@dataclass
class ViewContext:
    screen_size: tuple[int, int]
    midi_input: MidiInput | None
    audio: AudioEngine
    progress_db: ProgressDB
    plugin_manager: PluginManager
    settings: Settings
    song: Song | None = None
    section: tuple[int, int] | None = None  # (start_bar, end_bar)
    hand: Hand = Hand.BOTH
    tempo_scale: float = 1.0
```

### ViewAction

Navigation commands returned by views to the `ViewManager`:

```python
@dataclass
class ViewAction:
    kind: Literal["push", "pop", "switch", "quit"]
    target: str | None = None      # view name for push/switch
    context_patch: dict | None = None  # partial updates to ViewContext
```

- **push** — overlay a new view on the stack (e.g., pause menu over gameplay).
- **pop** — return to the previous view.
- **switch** — replace the current view entirely (e.g., menu → gameplay).
- **quit** — exit the application.

---

## ViewManager

Owns the view stack and dispatches the game loop to the active view.

```python
class ViewManager:
    def __init__(self, context: ViewContext) -> None:
        self._registry: dict[str, type[View]] = {}
        self._stack: list[View] = []
        self._context = context

    # -- Registration --

    def register(self, view_cls: type[View]) -> None:
        """Register a view class by its `name` attribute."""
        instance = view_cls()
        self._registry[instance.name] = view_cls

    def register_plugin_views(self, plugin_manager: PluginManager) -> None:
        """Discover and register views from plugins."""
        for view_cls in plugin_manager.get_view_plugins():
            self.register(view_cls)

    def list_views(self) -> list[tuple[str, str]]:
        """Return (name, display_name) for all registered views."""
        return [
            (name, cls().display_name)
            for name, cls in self._registry.items()
        ]

    # -- Navigation --

    def push(self, view_name: str, **context_overrides) -> None:
        """Push a new view onto the stack."""
        if self._stack:
            self._stack[-1].on_exit()
        view = self._registry[view_name]()
        ctx = self._apply_overrides(context_overrides)
        view.on_enter(ctx)
        self._stack.append(view)

    def pop(self) -> None:
        """Pop the current view and resume the previous one."""
        if self._stack:
            self._stack.pop().on_exit()
        if self._stack:
            self._stack[-1].on_enter(self._context)

    def switch(self, view_name: str, **context_overrides) -> None:
        """Replace the current view entirely."""
        if self._stack:
            self._stack.pop().on_exit()
        self.push(view_name, **context_overrides)

    # -- Game loop delegation --

    @property
    def active_view(self) -> View | None:
        return self._stack[-1] if self._stack else None

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Delegate event to active view. Returns False on quit."""
        if (view := self.active_view) is None:
            return False
        action = view.handle_event(event)
        return self._process_action(action)

    def update(self, dt: float) -> bool:
        """Delegate update. Returns False on quit."""
        if (view := self.active_view) is None:
            return False
        action = view.update(dt)
        return self._process_action(action)

    def draw(self, surface: pygame.Surface) -> None:
        """Delegate draw to active view."""
        if (view := self.active_view) is not None:
            view.draw(surface)

    def _process_action(self, action: ViewAction | None) -> bool:
        if action is None:
            return True
        if action.kind == "quit":
            return False
        elif action.kind == "push":
            self.push(action.target, **(action.context_patch or {}))
        elif action.kind == "pop":
            self.pop()
        elif action.kind == "switch":
            self.switch(action.target, **(action.context_patch or {}))
        return True
```

---

## Updated App Integration

```python
class App:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()

        context = ViewContext(
            screen_size=(WINDOW_WIDTH, WINDOW_HEIGHT),
            midi_input=MidiInput() if MidiInput.available() else None,
            audio=AudioEngine(),
            progress_db=ProgressDB(),
            plugin_manager=PluginManager(),
            settings=Settings.load(),
        )

        self.views = ViewManager(context)

        # Register built-in views
        self.views.register(MenuView)
        self.views.register(WaterfallView)
        self.views.register(PracticeView)
        self.views.register(FreePlayView)

        # Register plugin views
        self.views.register_plugin_views(context.plugin_manager)

        # Start on the menu
        self.views.push("menu")

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    running = self.views.handle_event(event)
            if running:
                running = self.views.update(dt)
            self.views.draw(self.screen)
            pygame.display.flip()

        pygame.quit()
```

---

## Built-in Views

### 1. MenuView (`name = "menu"`)

**Layout:** Song list on the left, preview/settings panel on the right.

**Responsibilities:**
- List available MIDI/MusicXML files from a configurable song directory.
- Show song metadata (title, duration, difficulty estimate, best score).
- Let the user pick a game mode before launching:
  - "Play" → `switch("waterfall", song=selected_song)`
  - "Practice" → `switch("practice", song=selected_song)`
  - "Free Play" → `switch("freeplay")`
- Show registered plugin views as additional entries.
- Access to settings (tempo default, MIDI device, SoundFont, accessibility).

**Key Events:**
| Key | Action |
|-----|--------|
| ↑/↓ | Navigate song list |
| Enter | Launch selected mode |
| Tab | Cycle mode (Play / Practice / Free Play) |
| Esc | Quit app |
| S | Open settings overlay (push) |

---

### 2. WaterfallView (`name = "waterfall"`)

**Layout:** (see `docs/mockups/01_classic_waterfall.png`)

| Region | Content |
|--------|---------|
| Top bar (44px) | Logo, song title, score, streak, accuracy, elapsed time |
| Main area | Falling note bars — blue (RH), orange (LH) |
| Right sidebar (80px) | Mode, tempo, hands toggle |
| Hit line (3px) | Yellow line just above keyboard |
| Keyboard (110px) | 88-key piano, keys light up on hit |
| Bottom legend | Hand color key |

**Responsibilities:**
- Render the waterfall via `renderer/waterfall.py`.
- Delegate hit detection to `evaluator.py`.
- Manage playback state (play, pause, restart).
- Support wait mode via `playback.py`.
- Display HUD via `renderer/hud.py`.

**Key Events:**
| Key | Action |
|-----|--------|
| Space | Pause / Resume |
| Esc | Pop back to menu |
| W | Toggle wait mode |
| ←/→ | Seek backward/forward 4 bars |
| +/- | Adjust tempo ±5% |
| 1/2/3 | Switch hand: both / right / left |
| R | Restart song from beginning |

**Sub-Components (composable panels):**
```
WaterfallView
├── HudPanel          (top bar — score, time, song info)
├── WaterfallPanel    (falling notes area)
├── SidebarPanel      (mode/tempo/hands controls)
├── KeyboardPanel     (88-key piano)
└── LegendPanel       (hand color legend)
```

Each panel implements a lightweight `Panel` protocol:

```python
class Panel(Protocol):
    def layout(self, rect: pygame.Rect) -> None: ...
    def handle_event(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: pygame.Surface) -> None: ...
```

Panels can be reused across views. `KeyboardPanel` appears in all three gameplay views. `HudPanel` appears in waterfall and practice.

---

### 3. PracticeView (`name = "practice"`)

**Layout:** (see `docs/mockups/02_practice_mode.png`)

| Region | Content |
|--------|---------|
| Top bar (44px) | Logo, song title, practice context |
| Notation panel (180px) | Grand staff with scrolling cursor |
| Waterfall area | Bounded by section loop markers |
| Left sidebar (180px) | Practice controls |
| Right sidebar (180px) | Per-loop stats and best run |
| Hit line | Yellow |
| Keyboard (110px) | 88-key piano |

**Responsibilities:**
- Everything in WaterfallView, plus:
- Render notation via `notation.py`.
- Section selection and looping via `playback.py` (`select_section`).
- Split hands: active hand in full color, inactive hand ghosted and auto-played.
- Track per-loop and per-session stats.
- Metronome toggle (audio tick via `audio.py`).

**Key Events:**
| Key | Action |
|-----|--------|
| Space | Pause / Resume |
| Esc | Pop back to menu |
| W | Toggle wait mode |
| L | Toggle loop |
| [ / ] | Move section start/end by 1 bar |
| Shift+[ / Shift+] | Move section start/end by 4 bars |
| +/- | Adjust tempo ±5% |
| 1/2/3 | Switch hand |
| M | Toggle metronome |
| N | Toggle notation panel visibility |
| R | Restart section |

**Sub-Components:**
```
PracticeView
├── HudPanel
├── NotationPanel     (staff + scrolling cursor)
├── WaterfallPanel    (reused, with section bounds)
├── PracticeSidebar   (left — controls)
├── StatsSidebar      (right — loop stats, best run)
├── KeyboardPanel
└── SectionMarkers    (loop start/end overlay)
```

---

### 4. FreePlayView (`name = "freeplay"`)

**Layout:** (see `docs/mockups/03_free_play.png`)

| Region | Content |
|--------|---------|
| Top bar (44px) | Logo, "Free Play" label, REC indicator |
| Chord display (120px) | Large chord name, component notes, quality badge |
| Chord history (80px) | Horizontal scrolling timeline of detected chords |
| Note trail (250px) | Left-scrolling visualization of played notes |
| Keyboard (120px) | 88-key piano with active keys lit, note labels |
| Bottom bar | Instrument selector, Export MIDI button, sustain indicator |

**Responsibilities:**
- No song loaded — purely reactive to player input.
- Real-time chord detection (map held notes → chord name + quality).
- Maintain a scrolling chord history buffer.
- Render a horizontal note trail (piano-roll scrolling left).
- Optionally record all input to a MIDI buffer for export.
- SoundFont selection for different instrument timbres.
- Sustain pedal state display (CC64).

**Key Events:**
| Key | Action |
|-----|--------|
| Esc | Pop back to menu |
| R | Toggle recording |
| E | Export recording to MIDI file |
| I | Cycle instrument / SoundFont preset |
| C | Toggle chord detection overlay |
| T | Toggle note trail |

**Sub-Components:**
```
FreePlayView
├── HudPanel          (minimal — logo, mode, rec indicator)
├── ChordDisplay      (large chord name + notes)
├── ChordTimeline     (scrolling history)
├── NoteTrail         (horizontal scrolling piano roll)
├── KeyboardPanel     (reused, with note labels)
└── ToolbarPanel      (instrument, export, sustain)
```

---

## Plugin View Registration

Plugins add views via the `keyfall.views` entry point group:

```toml
# Plugin's pyproject.toml
[project.entry-points."keyfall.views"]
my_custom_view = "my_plugin.views:MyCustomView"
```

The plugin class implements the `View` protocol:

```python
class MyCustomView:
    name = "rhythm_game"
    display_name = "Rhythm Game Mode"

    @property
    def icon(self) -> str:
        return "🥁"

    def on_enter(self, context: ViewContext) -> None:
        self.song = context.song
        self.audio = context.audio
        # ... setup ...

    def on_exit(self) -> None:
        # ... cleanup ...

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return ViewAction(kind="pop")
        return None

    def update(self, dt: float) -> ViewAction | None:
        # ... game logic ...
        return None

    def draw(self, surface: pygame.Surface) -> None:
        # ... custom rendering ...
        pass
```

Plugin views appear in the menu alongside built-in views, distinguished by a "Plugin" badge.

### Plugin Panels

Plugins can also contribute individual panels to existing views:

```python
class PanelPlugin(Protocol):
    name: str
    target_view: str  # e.g. "waterfall"
    anchor: Literal["top", "bottom", "left", "right", "overlay"]
    size: int  # pixels for the anchored edge

    def layout(self, rect: pygame.Rect) -> None: ...
    def handle_event(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: pygame.Surface) -> None: ...
```

```toml
[project.entry-points."keyfall.panels"]
combo_counter = "my_plugin.panels:ComboCounterPanel"
```

This lets plugins add an overlay (e.g., particle effects, combo counter) to the waterfall view without replacing it entirely.

---

## View Lifecycle

```
App starts
  │
  ├── ViewManager created
  ├── Built-in views registered
  ├── Plugin views discovered and registered
  │
  ├── push("menu")
  │     └── MenuView.on_enter(context)
  │
  │   User selects "Play" with a song
  │     └── switch("waterfall", song=...)
  │           ├── MenuView.on_exit()
  │           └── WaterfallView.on_enter(context)
  │
  │   User presses Esc during gameplay
  │     └── pop()
  │           ├── WaterfallView.on_exit()
  │           └── MenuView.on_enter(context)
  │
  │   User selects a plugin view
  │     └── switch("rhythm_game", song=...)
  │           └── MyCustomView.on_enter(context)
  │
  └── quit → all views popped, on_exit() called, pygame.quit()
```

---

## Shared Panels Catalog

| Panel | Used In | Description |
|-------|---------|-------------|
| `HudPanel` | waterfall, practice, freeplay | Top bar with logo, context info |
| `KeyboardPanel` | waterfall, practice, freeplay | 88-key piano at bottom |
| `WaterfallPanel` | waterfall, practice | Falling notes (accepts section bounds) |
| `NotationPanel` | practice | Grand staff with cursor |
| `SidebarPanel` | waterfall | Mode/tempo/hands controls |
| `PracticeSidebar` | practice | Full practice controls |
| `StatsSidebar` | practice | Per-loop and best-run stats |
| `ChordDisplay` | freeplay | Large chord name + quality |
| `ChordTimeline` | freeplay | Scrolling chord history |
| `NoteTrail` | freeplay | Horizontal scrolling piano roll |
| `ToolbarPanel` | freeplay | Instrument, export, sustain |
| `SectionMarkers` | practice | Loop boundary overlay |
| `LegendPanel` | waterfall | Hand color legend |

---

## Layout Engine

Views compose panels using a simple rect-subdivision approach:

```python
def layout_regions(
    total: pygame.Rect,
    specs: list[tuple[str, Literal["top", "bottom", "left", "right"], int]],
) -> dict[str, pygame.Rect]:
    """Carve out named regions from total rect.

    Each spec is (name, anchor, size_px). Remaining space
    is returned as "center".
    """
    remaining = total.copy()
    regions: dict[str, pygame.Rect] = {}

    for name, anchor, size in specs:
        if anchor == "top":
            regions[name] = pygame.Rect(remaining.x, remaining.y, remaining.w, size)
            remaining = pygame.Rect(remaining.x, remaining.y + size, remaining.w, remaining.h - size)
        elif anchor == "bottom":
            regions[name] = pygame.Rect(remaining.x, remaining.bottom - size, remaining.w, size)
            remaining = pygame.Rect(remaining.x, remaining.y, remaining.w, remaining.h - size)
        elif anchor == "left":
            regions[name] = pygame.Rect(remaining.x, remaining.y, size, remaining.h)
            remaining = pygame.Rect(remaining.x + size, remaining.y, remaining.w - size, remaining.h)
        elif anchor == "right":
            regions[name] = pygame.Rect(remaining.right - size, remaining.y, size, remaining.h)
            remaining = pygame.Rect(remaining.x, remaining.y, remaining.w - size, remaining.h)

    regions["center"] = remaining
    return regions
```

Example for WaterfallView:

```python
regions = layout_regions(
    pygame.Rect(0, 0, 1280, 800),
    [
        ("hud", "top", 44),
        ("keyboard", "bottom", 110),
        ("legend", "bottom", 20),
        ("sidebar", "right", 80),
    ],
)
# regions["center"] = the waterfall area (auto-sized)
```

---

## Testing Plan

| Test | Assertion |
|------|-----------|
| View protocol check | `isinstance(WaterfallView(), View)` is True |
| ViewManager.register | view appears in list_views |
| ViewManager.push/pop | stack depth changes correctly |
| ViewManager.switch | old view's on_exit called, new on_enter called |
| ViewAction("quit") stops loop | App.run returns |
| Plugin view discovery | entry point view appears in registry |
| Panel reuse | KeyboardPanel works in all 3 views |
| layout_regions carves correctly | center rect is remainder |
| PanelPlugin overlay | plugin panel drawn on top of base view |
| on_exit called on quit | resource cleanup verified |

## Dependencies

- `pygame` (LGPL)
- `dataclasses`, `typing` (stdlib)
- Plugin views: `importlib.metadata` (stdlib)

## Open Questions

- Should views support transition animations (fade, slide)?
- Should the layout engine support percentage-based sizing in addition to pixel-based?
- Should there be a `PauseOverlayView` that can be pushed on top of any gameplay view?
- Should views declare their minimum window size?
