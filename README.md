# ![](./assets/felis_small.svg) Felis

> **★ Star the repo to support the project!**

[![GitHub stars](https://img.shields.io/github/stars/Felis-Language/Felis?style=flat&label=stars&logo=github)](https://github.com/Felis-Language/Felis)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Felis is a text-first programming language that compiles to Scratch 3.0 (`.sb3`) projects. It enables writing Scratch projects using structured, version-controlled source files and a concise, readable syntax.

Quick highlights:

- Compile Felis source into Scratch `.sb3` files
- Support for functions, modules, and common programming abstractions
- Designed to make larger Scratch projects maintainable with standard tools (Git, editors, CI)


---

## Getting started

Clone the official repository and install for development:

```bash
git clone https://github.com/Felis-Language/Felis.git
cd Felis
pip install -e .
```

Create a simple file `hello.felis`:

```felis
sprite Cat {
  on flag {
    say("Hello from Felis!")
  }
}
```

Compile to an `.sb3`:

```bash
python -m felis.cli hello.felis -o hello.sb3
```

Full documentation is in the `docs/` folder. Start here:

- [Getting Started](docs/getting_started.md)
- [Language Reference](docs/language_reference.md)
- [Syntax & Runtime](docs/syntax_and_runtime.md)
- [Standard Library](docs/stdlib.md)

---

## Contributing

Contributions are welcome via Pull Requests. See `CONTRIBUTING.md` for guidelines, coding conventions, and the project's stance on AI-assisted code.

If you're developing locally, the above `pip install -e .` setup is sufficient to run the compiler module.

---

## Community

Report issues, request features, or discuss the project on GitHub:

- Issues: https://github.com/Felis-Language/Felis/issues
- Pull requests: https://github.com/Felis-Language/Felis/pulls

---

## License

This project is licensed under the MIT License — see the `LICENSE` file for details.

---