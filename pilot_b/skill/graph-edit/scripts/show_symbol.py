"""show_symbol: print one symbol's source (or a file's symbol outline) as JSON.

args: symbol=<pkg.mod.Class.method | path/file.py:Class.method | Class.method | path/file.py>
      max_lines=<int, default 150>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _symlib  # noqa: E402

_symlib.run(_symlib.show_symbol, ["symbol"], aliases={"symbol": ["name", "node", "qualified_name", "path"]})
