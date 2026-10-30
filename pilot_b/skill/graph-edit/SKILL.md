---
name: graph-edit
description: View and change Python code by symbol name (pkg.module.Class.method) instead of copying exact text. Use it to read a function/class and to replace or add whole functions, methods or classes. The edit is syntax-checked before it is written.
---
# graph-edit: edit code by symbol name

Symbol names are the dotted names the code-graph tools print, e.g.
`fastapi.routing.APIRoute.__init__`. You can also write `path/to/file.py:Class.method`
or a unique short name such as `APIRoute.__init__`.

## 1. Look at a symbol
run_skill_script(skill_name="graph-edit", file_path="scripts/show_symbol.py",
                 args={"symbol": "fastapi.routing.APIRoute.__init__"})
Returns JSON: file, line range, and the full `source`. Pass a file path
(`args={"symbol": "fastapi/routing.py"}`) to list every symbol in that file.

## 2. Replace a whole function, method or class
run_skill_script(skill_name="graph-edit", file_path="scripts/edit_symbol.py",
                 args={"symbol": "fastapi.routing.APIRoute.__init__",
                       "new_source": "def __init__(self, path: str) -> None:\n    self.path = path\n"})
- `new_source` is the COMPLETE new definition (def line + full body), not a fragment.
- Indentation is fixed for you: write it starting at column 0.
- Decorators: if you leave them out, the existing decorators are kept.
- The file is only written if the result is valid Python. On error you get
  `"status": "error"` and the file is unchanged; fix `new_source` and retry.
- The reply contains a short diff of what changed. Check it.

## 3. Add a NEW function, method or class
run_skill_script(skill_name="graph-edit", file_path="scripts/insert_symbol.py",
                 args={"new_source": "def helper(x):\n    return x\n",
                       "after": "fastapi.routing.APIRoute.__init__"})
Use exactly one of `after`, `before`, or `into` (a class name, or a file path to append at the end).

## When NOT to use it
Imports and other module-level lines (constants, `__all__`) are not symbols: change those
with edit_file. Never edit test files.
