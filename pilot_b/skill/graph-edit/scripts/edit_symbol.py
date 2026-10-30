"""edit_symbol: replace a whole def/class by name; validated with ast before writing.

args: symbol=<name as in show_symbol> and EITHER
      new_source=<complete new definition>   (allow_rename=<true|false, default false>)
      OR old_string=<text inside the symbol> new_string=<replacement>  (match scoped to the symbol)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _symlib  # noqa: E402

_symlib.run(_symlib.edit_symbol, ["symbol"],
            aliases={"symbol": ["name", "node", "qualified_name"], "new_source": ["source", "code", "new_code"],
                     "old_string": ["old", "old_str"], "new_string": ["new", "new_str"]})
