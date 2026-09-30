# Pythonista Tools Installer

A front-end UI program to browse and/or download scripts listed on
[Pythonista-Tools](https://github.com/Pythonista-Tools/Pythonista-Tools).

## Installation

Download `ptinstaller.py` from this security-patched package. Review it before
running it in Pythonista. Avoid HTTP URL shorteners and one-line commands that
download executable code without showing its source. Record the package's
SHA-256 digest if you need to reproduce the installation later.

## Configuration

To customize the directory modules are installed to, create a file named `ptinstaller.conf` with below content:

```json
{
    "install_path": "bin",
    "trusted_sha256": {}
}
```

`install_path` must be a single directory name under `~/Documents`.
`trusted_sha256` maps an exact tool URL to a SHA-256 digest obtained from an
independent, reviewed copy of that tool. **Installation is refused if the URL
has no trusted digest.** GitHub digests cover the ZIP archive bytes. Gist
digests cover sorted UTF-8 filename/content pairs, each preceded by its
8-byte big-endian length. The installer records the GitHub commit fetched and
the downloaded archive digest
in `.ptinstaller-installed.json` inside the installation directory. GitHub
repositories are fetched at one resolved commit rather than a moving branch.

For a GitHub tool, inspect the repository and resolve its intended commit,
download that exact commit's ZIP from GitHub over HTTPS on a trusted machine,
and calculate `sha256sum archive.zip`. Record the result under the exact
catalog URL. The installer will download the current default-branch commit;
it succeeds only if those bytes match the reviewed ZIP. A changed archive
fails visibly and leaves the destination untouched. For Gists, use the
specified canonical content format to generate the digest from a reviewed
snapshot. Do not use a digest copied from the same unreviewed catalog as the
download URL.

Example after separately reviewing and hashing an archive:

```json
{
    "install_path": "bin",
    "trusted_sha256": {
        "https://github.com/example/tool": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
}
```

The example digest is a placeholder, not a real trusted digest. Review the
actual tool code before running it. The installer does not execute it.

The security design, compatibility notes, trust boundaries, and remaining
limitations are in [SEC-001](docs/SEC-001-installer-security-design.md).

## Usage
Execute the saved `ptinstaller.py` program to launch the UI. Follow the
on-screen instruction to browse and install/uninstall scripts. The scripts are by default installed under **`~/Documents/bin/`**.
An existing tool directory is never overwritten. The installer removes only
directories containing its matching installation marker. Older installations
made without a marker require manual review and removal.

### Screenshots

![1](https://cloud.githubusercontent.com/assets/2344308/9724048/58480568-5614-11e5-9403-d986adf82727.JPG) ![2](https://cloud.githubusercontent.com/assets/2344308/9724050/5e3736e2-5614-11e5-95ba-7333ec7c952d.JPG)
