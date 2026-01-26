# Syntax and runtime

Felis programs compile into Scratch 3.0 projects. This page describes the event model and how source constructs map to the Scratch runtime.

Event model

- `on flag` runs when the green flag is clicked.
- `on clone` runs when a sprite is cloned.
- Input handlers (keys, mouse) are compiled into event listeners.

Concurrency

Each handler is compiled to a separate Scratch script that runs concurrently. Avoid shared mutable state without careful synchronization.

Broadcasts and messages

Use broadcasts to communicate between sprites. Felis provides helper functions for broadcasting.

Runtime considerations

- Scratch has limited primitive types. Felis maps higher-level constructs into Scratch-compatible representations.
- Avoid very large data structures; prefer storing and serializing compact values.

Limitations

- Precise floating point behavior is limited by the Scratch runtime.
- Timers and scheduling are cooperative; long-running loops can block event handling if not written carefully.

Debugging

- Compile to `.sb3` and open the project in the Scratch editor to inspect generated scripts.
- Use small, isolated examples when diagnosing compilation issues.
