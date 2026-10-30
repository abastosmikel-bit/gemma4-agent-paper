"""edit_symbol: replace a whole def/class by name; validated with ast before writing.

args: symbol=<name as in show_symbol>  new_source=<complete new definition>
      allow_rename=<true|false, default false>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _symlib  # noqa: E402

_symlib.run(_symlib.edit_symbol, ["symbol", "new_source"],
            aliases={"symbol": ["name", "node", "qualified_name"], "new_source": ["source", "code", "new_code", "new_string"]})
