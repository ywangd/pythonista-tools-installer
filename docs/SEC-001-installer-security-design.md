# SEC-001 — Installer security design

Status: Review candidate
Owner: This standalone installer package
Source baseline: `ywangd/pythonista-tools-installer` commit
`72128afceba22f773f835f60e1c5213a99033f90` (2016-04-18)

## Scope and authority

This design applies only to this Pythonista Tools installer. It borrows the
documentation, evidence, recovery, and security discipline of Catalyst's
AES-DEV-001; it does not make this external repository a Catalyst project or
subject it to AEMS enforcement. The upstream repository owns its code. This
package is a proposed downstream patch until the maintainer accepts it.

## Trust boundaries

1. The Pythonista Tools catalog is remote metadata. Category names, tool
   names, and URLs have no filesystem authority.
2. GitHub archives and Gists are remote content. TLS authenticates the
   transport endpoint, not the publisher's intent or code quality.
3. The local `ptinstaller.conf` is the operator's trust decision: an exact
   catalog URL must have a SHA-256 digest established independently from a
   reviewed copy. The configuration file itself must be protected by the
   device's normal filesystem controls.
4. The installer writes within `~/Documents/<install_path>/<category>/<tool>`.
   Installed scripts are data until the user runs them. They then have the
   authority available to Pythonista; the installer does not sandbox them.

## Installation contract (v1.1.0-security)

- `install_path`, category, and tool names are individual path components;
  separators, traversal, controls, and empty names are rejected.
- GitHub and Gist source recognition accepts exact HTTPS hosts and path forms.
  Other catalog links open only if they use HTTPS; they are not reported as
  installed. Network responses have timeouts, status checks, redirect host
  checks, and size limits.
- A GitHub default branch is resolved to a commit before archive download.
  Archive members are bounded in count and size; traversal, symlinks, unusual
  file types, and duplicate output names are rejected. Gist names and content
  are checked and bounded. SHA-256 is checked before promotion.
- An install is prepared in a new temporary directory under the category.
  A matching receipt is written there. The directory is renamed to the final
  target only after all checks pass. Any preexisting target is preserved.
- A failure removes only that attempt's temporary directory and reports the
  error. The remote catalog, archive, and existing user directories remain
  untouched.
- Uninstall requires a matching receipt and rejects symlinks. Directories
  without a receipt, including installations from the original program, need
  manual review and migration.

## Failure and recovery

| Condition | Result | Recovery |
| --- | --- | --- |
| Missing or mismatched digest | No install; existing files preserved | Review the exact source revision; update local trust entry |
| Invalid archive, Gist, or URL | Temporary files removed | Inspect source and catalog entry |
| Existing target directory | No overwrite or deletion | Inspect it and remove or migrate it manually |
| Unmanaged or modified install receipt | Uninstall refused | Inspect the directory manually |
| Network timeout or response too large | No install; error displayed | Retry after checking source and network |

## Compatibility and limitations

The original UI and catalog browsing remain. The intentional compatibility
break is that installs now require a trusted digest; existing tool directories
are never replaced, and legacy directories cannot be uninstalled through the
new UI. There is no automatic migration or rollback of older installs.
The loading spinner is optional; when `ui.ActivityIndicator` is absent in a
Pythonista build, background operations continue without that visual widget.

The ZIP digest is of GitHub's archive bytes. If GitHub changes its archive
encoding for the same commit, installation safely fails until the new bytes
are independently reviewed. A trusted digest proves byte identity, not that
the reviewed code is benign. The code has not been exercised in the actual
Pythonista iOS runtime. Concurrent local processes that mutate directories
during an install are outside the tested threat model.

## Verification evidence

Run from the package root:

```sh
python3 -m py_compile ptinstaller.py
python3 -m unittest discover -s tests -v
git diff --check
```

The focused tests use mocked network and UI modules. They cover path and URL
rejection, ZIP traversal and symlinks, valid archive extraction, existing file
preservation, cleanup on failed staging and hash mismatch, refusal without a
trust entry, and managed/unmanaged uninstall. Passing these tests is local
structural evidence, not a claim of iOS runtime qualification or full audit.

## Design decision

Requiring the digest before download is a deliberate secure-default decision.
An optional digest would preserve the original one-click install behavior but
leave the primary supply-chain trust boundary open. The resulting workflow is
less convenient and provides a visible trust decision and deterministic
failure. This local design note records the tradeoff; it does not assert a
Catalyst governance decision.
