# SEC-002 — Security patch and session change record

Status: Review candidate
Owner: Standalone Pythonista Tools Installer patch
Prepared: 2026-09-29 through 2026-09-30 (America/Los_Angeles)
Upstream baseline: `ywangd/pythonista-tools-installer` commit
`72128afceba22f773f835f60e1c5213a99033f90` (2016-04-18)

## Purpose and authority

This record explains the complete patch series and its operational artifacts
so a maintainer can review and apply it to the upstream repository. The user
requested the development, documentation, and security *ideals* of Catalyst.
This installer is external to Catalyst: Catylist, AES, and AEMS do not govern
it, and this patch makes no claim of AEMS compliance. The repository itself
owns the implementation, design notes, tests, and decisions in this patch.

## Findings, changes, and reasons

| Original behavior or observed fault | Change | Reason and evidence |
| --- | --- | --- |
| Catalog category and tool names, Gist filenames, and ZIP member names reached filesystem joins without validation. | Check single path components and archive-relative paths; reject traversal, symlinks, and unsupported archive entries. | Remote metadata must not select arbitrary writable paths. Traversal and symlink tests exercise the rejection. |
| Failed installs removed `target_folder` even if it existed before this attempt; uninstall also used `shutil.rmtree` on a catalog-derived path. | Stage each install in a new temporary directory, verify it, then rename; refuse an existing target. Require a matching installation receipt before uninstall. | A failure must preserve user files. Existing-target, failed-staging, hash-mismatch, and unmanaged-uninstall tests cover these paths. |
| Archives were read into memory by member, with no bounded size or duplicate-entry checks. | Bound network downloads, archive count, each file, and expanded total; stream ZIP members; reject duplicate output names. | Control resource use and prevent ambiguous overwrites. These bounds are documented in `ptinstaller.py`; full stress testing on iOS remains open. |
| Loose URL matching accepted HTTP GitHub/Gist forms and paths beyond a repository root. The README bootstrapped executable code through an HTTP short link. | Require exact HTTPS hosts and supported URL forms; remove the short-link bootstrap; check response status, timeout, and redirect host. | Reduce transport and URL-confusion risks. URL rejection tests cover representative malformed inputs. |
| The installer followed a moving `master.zip` with no byte verification. | Resolve GitHub's default branch to one commit for a download and require an exact SHA-256 value in `trusted_sha256` before installation. Gist content uses a deterministic length-prefixed filename/content digest. | A reviewed byte pin detects changed content. The pin does not establish that the code is benign. Missing and mismatched hash tests cover failure behavior. |
| The first hash-config file stored observed values under `observed_sha256`, leaving `trusted_sha256` empty. | After the user requested active use, populate `trusted_sha256` in the dated example and user distribution config. Keep the default repository config empty. | The empty active field caused the reported `No trusted SHA-256 configured` errors. The dated allowlist is an explicit operator choice, not a code audit. |
| Initial tests printed tracebacks for expected refusal cases. | Capture those expected diagnostics in tests. | `Ran ... tests OK` should be readable without implying the installer itself failed. |
| The first bundled tests assigned a fake `ui` to `sys.modules` and failed to restore it. Subsequent installer runs in the same Pythonista process lacked `ActivityIndicator` and `TableView`. | Load the installer under scoped test doubles and restore the module cache; add a regression test. Also tolerate a missing spinner, which is not required for installer function. | The user's two screenshots identified these consecutive attributes; Pythonista's normal `ui` documents both. Restarting Pythonista clears a cache poisoned by an earlier test package. The spinner fallback alone was an incomplete diagnosis. |

## Catalog snapshot and hash provenance

The user requested SHA-256 values for every catalog tool. The catalog was
cloned at commit `507e19d8a81638c388acf3c486f51889c95d9936`. The parser
matching this installer's Markdown behavior found **144 listings** with
**136 distinct URLs**. For 71 GitHub repositories, the default `HEAD` commit
was resolved and that commit's ZIP bytes were hashed. For 47 Gists, the
installer-compatible Python and `.pyui` content was hashed in sorted filename
order, each UTF-8 filename and content preceded by an 8-byte big-endian
length. Thus **118 distinct digests cover 126 listings**. The snapshot's
`generated_utc`, exact URLs, revisions, and checksums are in
`examples/ptinstaller-catalog-snapshot-2026-09-29.conf`.

Of the other 18 distinct URLs, 17 were app-store links or URL forms that this
installer does not recognize as downloadable GitHub/Gist roots; one ZIP
exceeded the 50 MiB download limit. Each is listed under `_catalog_audit.issues`
in the example. These are observed results for that snapshot, not a promise
that an upstream repository remains unchanged. A changed ZIP encoding or
content may produce a mismatch even at the same commit.

The example deliberately carries both `observed_sha256` and the
operator-requested active `trusted_sha256` mapping. In this setting, “trusted”
means **approved for byte matching by the operator**, not “source reviewed and
safe.” The code of 118 tools was not individually audited. The checked-in
`ptinstaller.conf` has an empty allowlist as the secure default. A user who
accepts the dated snapshot can copy the example beside `ptinstaller.py`; they
should review any script before running it. The installer never executes the
downloaded script automatically.

## Change sequence and decision trail

1. Inspected the original source and identified unsafe path/deletion and
   mutable download behavior.
2. Added path/URL validation, bounded downloads and extraction, staged
   installation, receipt-guarded uninstall, and security documentation.
3. Changed an initially optional hash check to a required check. This is an
   intentional compatibility break, recorded in `SEC-001` and the README.
4. Built a focused mocked test suite. The first distributed test suite had
   noisy expected errors, then caused module-cache contamination on iOS.
5. Parsed and hashed the dated catalog; first retained checksums as observed
   data, then activated the 118 values at the user's direction.
6. Added iPad installation guidance, quieted expected test failures, handled
   the spinner without making it mandatory, and isolated all test doubles.
7. Preserved the full dated catalog configuration as an example while leaving
   the repository default fail-closed. This patch does not alter Catalyst
   repositories or publish changes to the upstream GitHub repository.

## Verification and limits

Run in a clean checkout after applying the patch:

```sh
python3 -m py_compile ptinstaller.py
python3 -m json.tool ptinstaller.conf > /dev/null
python3 -m json.tool examples/ptinstaller-catalog-snapshot-2026-09-29.conf > /dev/null
python3 -m unittest discover -s tests -v
git diff --check
```

The test suite contains 13 focused cases and uses mocked network/UI modules;
it has passed locally. The screenshot failures supplied by the user are
runtime evidence of the module-cache defect, and the regression test proves
the new loader restores `sys.modules['ui']` in the tested interpreter. The
patched installer has **not** been qualified end to end in Pythonista on the
user's device. No claim is made that the catalog scripts are safe, that every
ZIP can be installed, or that future GitHub archives remain byte-identical.

## Applying and reviewing

The distributed `security.patch` is a concatenated `git format-patch` series
from the upstream baseline above. On a clean branch based on that commit:

```sh
git am --3way security.patch
python3 -m unittest discover -s tests -v
```

Inspect every commit and the dated allowlist example before merging. The
example is a record of a user-approved byte snapshot and may be excluded from
an upstream release policy without changing the installer's fail-closed
default. Older installations without a receipt require manual review and
migration; the new uninstall action refuses them.
