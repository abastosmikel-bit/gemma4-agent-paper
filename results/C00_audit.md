# Benchmark audit: why each invalid dev task is invalid (data only)

Valid = the gold patch passes AND no patch fails, in the official sandbox (Kaggle, `notebooks/C00_gold_check__CPU.ipynb`). Valid: 71/129. Invalid: 58. Produced by `pilot_c/audit_table.py` from `results/C00_gold_check.json` and `results/C00_audit_imports.json`.

## Reasons (counts)

| Category | Tasks |
|---|---|
| A. test dependency missing in the sandbox image | 34 |
| B1. host's installed package shadows the repo (valid once src/ is imported) | 6 |
| B2. host's installed package shadows the repo, and a test fixture is missing | 8 |
| C. test plugin missing | 2 |
| D. environment-dependent expected output | 5 |
| E. required test skipped on the sandbox's Python | 1 |
| F. tests pass with no patch | 2 |

## Import check controls (valid tasks, same probe)

| Task | layout | imported from (as the harness runs) |
|---|---|---|
| fastapi_15588 | root | workspace 0.136.1 |
| rich_3470 | root | workspace  |

## Per task

| Task | Repo | Gold (Kaggle) | No patch (Kaggle) | C00 class | Category | Reason | Evidence | Certainty |
|---|---|---|---|---|---|---|---|---|
| fastapi_11355 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_12942 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_13207 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_13713 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_13786 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14099 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14186 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14246 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14262 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14266 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14297 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14303 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14349 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14356 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14360 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14361 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14371 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals, inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14430 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14455 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14459 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14482 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14485 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14512 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14583 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14605 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals, inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14609 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14791 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): dirty_equals, inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14953 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14962 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14964 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_14978 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_15023 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_15030 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| fastapi_15745 | fastapi/fastapi | False | False | missing_module | A. test dependency missing in the sandbox image | missing module(s): inline_snapshot | Kaggle C00: ModuleNotFoundError | verified |
| httpx_3672 | encode/httpx | False | False | test_failure | B1. host's installed package shadows the repo (valid once src/ is imported) | tests import the host's installed httpx 0.28.1, not the repo (src layout), so the patch cannot change the outcome; valid once src/ is imported | import check: host copy; with the repo's src/ first: gold=True, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_6644 | psf/requests | True | True | resolved | B1. host's installed package shadows the repo (valid once src/ is imported) | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; valid once src/ is imported | import check: host copy; with the repo's src/ first: gold=True, no patch=False; Kaggle C00: gold=True, no patch=True | verified (local) |
| requests_7205 | psf/requests | False | False | test_failure | B1. host's installed package shadows the repo (valid once src/ is imported) | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; valid once src/ is imported | import check: host copy; with the repo's src/ first: gold=True, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_7309 | psf/requests | False | False | test_failure | B1. host's installed package shadows the repo (valid once src/ is imported) | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; valid once src/ is imported | import check: host copy; with the repo's src/ first: gold=True, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_7315 | psf/requests | False | False | test_failure | B1. host's installed package shadows the repo (valid once src/ is imported) | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; valid once src/ is imported | import check: host copy; with the repo's src/ first: gold=True, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_7427 | psf/requests | False | False | test_failure | B1. host's installed package shadows the repo (valid once src/ is imported) | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; valid once src/ is imported | import check: host copy; with the repo's src/ first: gold=True, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_6589 | psf/requests | False | False | missing_fixture | B2. host's installed package shadows the repo, and a test fixture is missing | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; also pytest fixture missing (pytest-httpbin): httpbin, httpbin_secure | import check: host copy; with the repo's src/ first: gold=False, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_6592 | psf/requests | False | False | missing_fixture | B2. host's installed package shadows the repo, and a test fixture is missing | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; also pytest fixture missing (pytest-httpbin): httpbin, httpbin_secure | import check: host copy; with the repo's src/ first: gold=False, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_6629 | psf/requests | False | False | missing_fixture | B2. host's installed package shadows the repo, and a test fixture is missing | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; also pytest fixture missing (pytest-httpbin): httpbin, httpbin_secure | import check: host copy; with the repo's src/ first: gold=False, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_6757 | psf/requests | False | False | missing_fixture | B2. host's installed package shadows the repo, and a test fixture is missing | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; also pytest fixture missing (pytest-httpbin): httpbin, httpbin_secure | import check: host copy; with the repo's src/ first: gold=False, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_7328 | psf/requests | False | False | missing_fixture | B2. host's installed package shadows the repo, and a test fixture is missing | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; also pytest fixture missing (pytest-httpbin): httpbin, httpbin_secure | import check: host copy; with the repo's src/ first: gold=False, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_7433 | psf/requests | False | False | missing_fixture | B2. host's installed package shadows the repo, and a test fixture is missing | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; also pytest fixture missing (pytest-httpbin): httpbin, httpbin_secure | import check: host copy; with the repo's src/ first: gold=False, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_7502 | psf/requests | False | False | missing_fixture | B2. host's installed package shadows the repo, and a test fixture is missing | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; also pytest fixture missing (pytest-httpbin): httpbin, httpbin_secure | import check: host copy; with the repo's src/ first: gold=False, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| requests_7505 | psf/requests | False | False | missing_fixture | B2. host's installed package shadows the repo, and a test fixture is missing | tests import the host's installed requests 2.34.2, not the repo (src layout), so the patch cannot change the outcome; also pytest fixture missing (pytest-httpbin): httpbin, httpbin_secure | import check: host copy; with the repo's src/ first: gold=False, no patch=False; Kaggle C00: gold=False, no patch=False | verified (local) |
| fastapi_15763 | fastapi/fastapi | False | False | test_failure | C. test plugin missing | required tests are `async def` and no async pytest plugin is active in the sandbox | pytest: 'async def functions are not natively supported' for the 3 required tests | verified |
| fastapi_15785 | fastapi/fastapi | False | False | test_failure | C. test plugin missing | required tests are `async def` and no async pytest plugin is active in the sandbox | same 3 tests, same pytest message | verified |
| rich_3064 | Textualize/rich | False | False | test_failure | D. environment-dependent expected output | expected ANSI output of syntax-highlighted markdown differs in this environment | test_markdown: test_markdown_render, test_inline_code fail on styled strings | cause of the difference not verified |
| rich_3130 | Textualize/rich | False | False | test_failure | D. environment-dependent expected output | expected ANSI output of syntax-highlighted markdown differs in this environment | same two markdown tests fail on styled strings | cause of the difference not verified |
| rich_3296 | Textualize/rich | False | False | test_failure | D. environment-dependent expected output | expected styled output differs: pygments picks the IPython lexer (IPython is installed on the host) | AssertionError 'IPython' == 'Python' plus ANSI-output mismatches | likely |
| rich_3469 | Textualize/rich | False | False | test_failure | D. environment-dependent expected output | expected ANSI output of syntax-highlighted markdown differs in this environment | test_inline_code fails on styled strings | cause of the difference not verified |
| rich_4070 | Textualize/rich | False | False | test_failure | D. environment-dependent expected output | expected styled output differs: pygments picks the IPython lexer (IPython is installed on the host) | AssertionError 'IPython' == 'Python' / 'ipython' == 'python' plus ANSI-output mismatches | likely |
| rich_3486 | Textualize/rich | False | False | harness_error | E. required test skipped on the sandbox's Python | the required test is skipped on Python >= 3.11; the sandbox runs 3.12 | the test patch marks the required test to be skipped on Python 3.11 and later; pytest reports it skipped | verified |
| fastapi_14077 | fastapi/fastapi | True | True | resolved | F. tests pass with no patch | tests pass with NO patch | Kaggle C00: gold and no-patch both pass | verified |
| fastapi_14851 | fastapi/fastapi | True | True | resolved | F. tests pass with no patch | tests pass with NO patch | Kaggle C00: gold and no-patch both pass | verified |
