# Install in Pythonista 3

1. Unzip the distribution in Files.
2. Keep `ptinstaller.py` and `ptinstaller.conf` in the **same folder**. If you
   imported only the Python file into Pythonista, import or copy the config
   into that exact Pythonista folder too.
3. Open `ptinstaller.py` in Pythonista and tap the Run button. Select a
   category and tap **Install** beside a tool.
4. Successful installs appear in the Pythonista script library under
   `bin/<category>/<tool>/`. Open and inspect a script before running it.

The `tests/test_security.py` file is a developer test suite. Its purpose is to
trigger unsafe cases and verify that the installer refuses them. A result of
`Ran 11 tests ... OK` is a successful test run; it does **not** install a tool.

The distributed `ptinstaller.conf` contains a catalog snapshot of 118
calculated checksums. The user requested that these be active in
`trusted_sha256`. They pin bytes from a particular GitHub/Gist snapshot; they
are not a code safety audit. The other 18 distinct catalog URLs were not
pin-able through this installer's URL rules or download size limit. See
`_catalog_audit` in the config for exact provenance and unresolved entries.

If a tool reports **no trusted SHA-256**, verify the running script's folder
contains the current config and that the catalog URL is one of the pinned
entries. If it reports **SHA-256 mismatch**, upstream content has changed;
inspect the new revision before updating the pin. If it reports **target
already exists**, the installer preserved a preexisting folder; inspect it
before removing or moving it. The installer does not automatically run the
downloaded scripts.
