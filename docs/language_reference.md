# Language reference

This page lists common Felis language constructs and short examples. This is a quick reference, not an exhaustive tutorial.

Sprites and handlers

```felis
sprite Player {
  on flag {
    // startup code
  }

  on key("space") {
    // handler for space key press
  }
}
```

Functions

```felis
fn add(a: int, b: int) -> int {
  return a + b
}
```

Variables and scope

- `let` for local variables inside functions or handlers.
- `const` for immutable values.
- Module-level variables are shared by sprites in the same compiled project.

Control flow

- `if`, `else`, `while`, and `for` are available with familiar syntax.

Types

Felis uses a small set of built-in types (number, string, bool) and allows simple user-defined structures. The compiler attempts sensible conversions when targeting Scratch primitives.

Comments

- `//` single-line comment
- `/* ... */` block comment

Operators

- Arithmetic: `+`, `-`, `*`, `/`, `//` (floor division)
- Comparisons: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Logical: `and`, `or`, `not`

Modules and imports

Use modules to organize code into multiple files. Importing pulls definitions into the current compilation unit.

```
import math
import ui as UI
```

For detailed examples, see `examples/hello` and the `docs/syntax_and_runtime.md` page for runtime mapping.
