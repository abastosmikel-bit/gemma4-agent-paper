"""insert_symbol: add a NEW def/class next to an existing symbol, or at the end of a class/file.

args: new_source=<complete definition>  and exactly one of
      after=<symbol> | before=<symbol> | into=<class symbol | path/file.py>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _symlib  # noqa: E402

_symlib.run(_symlib.insert_symbol, ["new_source"],
            aliases={"new_source": ["source", "code", "new_code"]})
