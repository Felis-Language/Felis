Thank you for your interest in contributing to Felis!

Getting started
- Fork the repository and create a branch for your change: `git checkout -b feat/your-feature`
- Keep changes focused and open a single pull request per logical change.

Reporting issues
- Provide a short title and clear reproduction steps. Include a minimal `.felis` example when relevant.

Pull requests
- Target the `main` branch and open a pull request with a clear description of the change.
- Reference related issues using `#<issue-number>`.
- Include tests or example usage when adding language features or fixing bugs.

Coding style
- Python: follow PEP 8. We recommend using `black` and `flake8` if you have them installed.
- Felis examples: prefer concise, well-documented snippets. Keep example assets small for repository inclusion.

Testing locally
- Install an editable development version: `pip install -e .`
- Run quick compile checks for examples: `python -m felis.cli examples/hello/hello.felis -o /tmp/test.sb3`

Commits and messages
- Use short, descriptive commit messages. Conventional Commits are recommended (for example: `feat: add parser optimization`).

Contribution license
- By contributing, you agree that your contributions will be licensed under the project `LICENSE`.

Thank you
- Thank you. We appreciate your contributions; please be patient during code review.

