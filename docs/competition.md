# Competitive Landscape

Analysis of piano learning apps and open-source alternatives, focused on how KeyFall can differentiate.

---

## Commercial Competitors

### Synthesia

| | |
|---|---|
| **Audio approach** | MIDI playback only — no synthesis engine, relies on device sound or connected keyboard |
| **Key features** | Falling-note display, wait mode, optional notation overlay, hand separation, finger number hints, lighted keyboard support, MusicXML import, 150 included songs + any MIDI file |
| **Pricing** | Free (limited) + one-time $39 Learning Pack |
| **Platforms** | Windows, macOS, iOS, Android |
| **Limitations** | No music theory instruction; no chord/scale teaching; encourages bypassing sheet music reading; no microphone support for acoustic pianos; purely a note-matching tool with no pedagogical depth |

### Simply Piano (JoyTunes)

| | |
|---|---|
| **Audio approach** | Real-time note recognition via device microphone or MIDI connection |
| **Key features** | 1,200+ songs, structured beginner-to-advanced curriculum, technique drills, theory modules, live instructor-led group sessions, cross-device progress sync |
| **Pricing** | ~$20/month, ~$100/year. 7-day trial |
| **Platforms** | iOS, Android, Web (limited — no mic on web) |
| **Limitations** | Web version lacks real-time feedback; no rewind in songs; aggressive note highlighting with no disable option; confusing family/individual plan gating |

### Flowkey

| | |
|---|---|
| **Audio approach** | Microphone pitch recognition for acoustic pianos, USB/MIDI for digital pianos |
| **Key features** | 1,500+ songs with multiple difficulty levels, split-screen notation + pianist video, wait/slow/fast modes, structured courses, hand separation |
| **Pricing** | Free tier (8 songs). Premium ~$20/month or ~$10/month billed annually. Family plan available |
| **Platforms** | iOS, Android, Web |
| **Limitations** | Note recognition unreliable (false stops mid-piece); limited advanced theory; no formal assessment or exam prep |

### Playground Sessions

| | |
|---|---|
| **Audio approach** | MIDI-based real-time feedback with green/red/pink note scoring. Mic recognition in beta |
| **Key features** | 100+ hours of video lessons, 2,000+ songs, Rookie/Intermediate/Advanced curriculum, gamification with medals/trophies, co-created with Quincy Jones |
| **Pricing** | Monthly $25, Annual $150, Lifetime $349. 7-day trial |
| **Platforms** | Windows, macOS, iOS, Android |
| **Limitations** | No custom music import; slow song additions; no progress reset; advanced jazz/classical theory lacking; mic feedback still beta-quality |

### Skoove

| | |
|---|---|
| **Audio approach** | AI note recognition via microphone, Bluetooth, or MIDI |
| **Key features** | "Listen, learn, play" method; 500+ interactive video lessons across 19 courses; AI real-time feedback; one-on-one lessons with real teachers (Skoove Duo); 7 languages |
| **Pricing** | Free tier. Premium ~$13/month (quarterly) or ~$10/month (annual) |
| **Platforms** | iOS, Android, Web |
| **Limitations** | Smaller content library (500 vs 1,200+); less advanced material; mic recognition quality varies |

### Piano Marvel

| | |
|---|---|
| **Audio approach** | USB/MIDI keyboard for real-time assessment. "Book mode" for acoustic pianos (no assessment) |
| **Key features** | 28,000+ songs and 1,200 lessons across 18 levels; SASR adaptive sight-reading tests; ABRSM exam prep; teacher tools; scales, arpeggios, ear training, flashcards |
| **Pricing** | Free tier (200+ songs). Premium ~$16-18/month or ~$110-120/year. 7-day trial |
| **Platforms** | Web (Mac/PC), iOS (iPad only). No Android |
| **Limitations** | No Android; acoustic piano mode lacks feedback; web-only on desktop; utilitarian UI; primarily MIDI-dependent |

### Yousician Piano

| | |
|---|---|
| **Audio approach** | Microphone real-time audio recognition + MIDI connection |
| **Key features** | 1,500+ missions, Classical/Knowledge/Pop paths, multiple notation options, adjustable tempo, hand separation, multi-instrument platform |
| **Pricing** | Free tier (limited daily practice). Premium ~$20/month or ~$120/year |
| **Platforms** | Windows, macOS, iOS, Android |
| **Limitations** | Shallow feedback — lacks detailed performance analysis; mediocre song arrangements; insufficient advanced material; multi-instrument jack-of-all-trades means piano depth suffers |

---

## Open-Source Alternatives

| Project | Description | Status |
|---------|-------------|--------|
| [Neothesia](https://github.com/PolyMeilex/Neothesia) | Modern Rust-based falling-note MIDI player with polished visuals | Actively maintained — strongest OSS competitor |
| [Linthesia](https://github.com/allan-simon/linthesia) | Fork of pre-0.6.1 open-source Synthesia. Falling-note MIDI player | Largely unmaintained |
| PianoBooster | Scrolling music stave with MIDI keyboard input. Most popular Linux option | Maintained |
| Sightread | Web-based sight-reading trainer | Active |
| Midiano | Web app that plays any MIDI file with interactive piano display | Active |

---

## Summary Comparison

| App | Audio Approach | Pricing | Theory Depth | Acoustic Support |
|-----|---------------|---------|-------------|-----------------|
| Synthesia | MIDI playback only | One-time $39 | None | No |
| Simply Piano | Mic + MIDI | ~$100/yr | Moderate | Yes (mic) |
| Flowkey | Mic + MIDI | ~$120/yr | Basic | Yes (mic) |
| Playground Sessions | MIDI + mic (beta) | ~$150/yr or $349 lifetime | Moderate | Beta |
| Skoove | AI mic + MIDI | ~$120/yr | Basic-Moderate | Yes (mic) |
| Piano Marvel | MIDI only | ~$120/yr | Deep (exam prep) | Partial |
| Yousician | Mic + MIDI | ~$120/yr | Basic | Yes (mic) |

---

## KeyFall Differentiation Opportunities

**No competitor does real piano synthesis well.** Every app either plays back raw MIDI samples or relies entirely on the user's own instrument for sound. This is KeyFall's primary opening.

Specific gaps to exploit:

1. **Synthesis quality** — All competitors use basic SoundFont/sample playback with no physical modeling. KeyFall's planned improvements (sympathetic resonance, half-pedaling, release samples, velocity-curve timbral morphing, soundboard convolution, adaptive latency) are features found only in professional virtual instruments costing $100-400, not in any learning app.

2. **Open source** — Synthesia is closed-source with a one-time fee. Simply Piano, Flowkey, and others are subscription SaaS. The only active OSS competitor is Neothesia (Rust), which has no audio synthesis, pedagogy, or evaluation. KeyFall can be the open-source piano learning engine that others build on.

3. **Extensibility** — No competitor offers a plugin system. KeyFall's planned plugin architecture (scoring, visualization, input, and view plugins) enables community-driven game modes and teaching methods.

4. **Latency** — Competitors accept default audio backend latency (40-50ms). KeyFall's adaptive latency engine with predictive voice pre-allocation targets <10ms on capable hardware.

5. **Expressive technique** — No app supports half-pedaling, key-off velocity, or continuous dynamics. Advanced students have no tool that rewards expressive playing.

6. **One-time cost / free** — Subscription fatigue is real. Synthesia proved one-time pricing works. KeyFall being free and open-source is the strongest value proposition possible.
