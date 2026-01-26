Felis Extensions
================

This folder would contain packaged extension descriptors (`*.felisx`) for third-party Scratch/TurboWarp extensions. I do not have any included here (yet), but I would suggest placing them in here if applicable.

Why extensions are separate
- Extensions bridge Felis code to external Scratch/TurboWarp extension scripts. They are not language core files, and are typically maintained by extension authors.

I recommend you keep reusable extension descriptors or implementation code in a separate companion repository (or in `felis/libs/`).

How extensions work (overview)
- A Felis extension descriptor is a JSON-like `.felisx` file that maps Felis function/command names to extension blocks and provides the extension ID and JS URL.
- At compile time, the compiler reads available extensions and emits the appropriate extension metadata into generated SB3 projects when code imports an extension symbol.
- THIS IS NOT A WAY TO CREATE NEW EXTENSIONS! In order for this to work, you have to have an existing extension with a website to link to it. I've not tested it without that; it probably won't work if you don't, though.

Creating a new extension descriptor
1. Start from an existing `.felisx` descriptor (see template in directory) and update fields:
   - `id` / `name` / `description`
   - `extensionUrl` / `scratchUrl` pointing to the extension JavaScript
   - Mapping table of `felisName` → extension block definition
2. You could probably test the mapping by writing a small Felis example that imports the mapped names and compiling to an SB3 using `python -m felis.cli`.
3. Host the extension JS on a reliable URL, again; will not work without that.

- See `felis/decompiler.py` and `felis/extensions.py` for examples of how extension metadata is parsed and used by the toolchain.
