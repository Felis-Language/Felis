# Standard library

Felis bundles a small standard library of utility modules that compile into the final project only when used.

Common modules

- `list` — list helpers and utilities
- `math` — math helpers
- `random` — random number utilities
- `logging` — lightweight logging helpers for development

Adding libraries

To add third-party or project-specific libraries, place them under `felis/libs/` and import them from your sources. Large or optional SDKs can be kept out of the core `felis/stdlib` and added as separate packages.

Tree-shaking

The compiler performs simple tree-shaking: unused stdlib functions are not emitted into the generated Scratch project.

Packaging notes

When publishing a library for others to use, include tests and a short README showing example usage.
