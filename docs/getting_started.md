# Getting started

This guide shows a minimal local setup for development and how to compile a simple Felis source file into an `.sb3` Scratch project.

Prerequisites

- Python 3.10 or newer
- `git`

Clone and install for development

```bash
git clone https://github.com/Felis-Language/Felis.git
cd Felis
pip install -e .
```

Create a minimal example `hello.felis`:

```felis
sprite Cat {
  on flag {
    say("Hello from Felis!")
  }
}
```

Compile to `.sb3`:

```bash
python -m felis.cli hello.felis -o hello.sb3
```

Tips

- Use an editor with Python and general-purpose language support (VS Code recommended).
- Keep small example projects in `examples/hello` to learn the toolchain.
- For CI, run a script that compiles examples and validates the generated `.sb3` files.
