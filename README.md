# PiGit extensions

The extensions PiGit has reviewed. Each entry pins one package in VS Code's
format by its SHA-256 and says what PiGit may use from it. PiGit's
Preferences › Extensions lists what is here and installs from it.

PiGit has no extension host. It reads an extension's colour themes and icon
themes as files and never loads its script. So an entry is a statement about
files: this package, with this hash, holds these themes.

## An entry

One file per extension, `extensions/<publisher>.<name>.toml`:

```toml
id = "catppuccin.catppuccin-vsc-icons"
version = "1.26.0"
summary = "Soothing pastel icons for files and folders, in the four Catppuccin flavours."
uses = ["icon-themes"]

[package.any]
url = "https://open-vsx.org/api/Catppuccin/catppuccin-vsc-icons/1.26.0/file/Catppuccin.catppuccin-vsc-icons-1.26.0.vsix"
sha256 = "57566136d0a8ba8d040eb6e5be866c88ccbb04f3d219d3a7e52a19978900ff3d"
size = 1946592
```

| Key | What it is |
|---|---|
| `id` | `publisher.name` as the package's own `package.json` has them, in lower case. The file is named after it. |
| `version` | The package's version. An update is a change of this line and of the package below it. |
| `summary` | One line, written here, at most 200 characters. |
| `uses` | What PiGit may use from the package: `colour-themes`, `icon-themes`, `interface-icons`. What a package brings beyond this is ignored. |
| `[package.any]` | The one package for every platform: where it is fetched from (https), its SHA-256 and its size in bytes. A package that differs by platform has `[package.linux-x64]`, `[package.darwin-arm64]` and so on in its place. |

The name a person reads, the licence, the repository, the themes by name and
the picture are not written here. They are read from the pinned package when
the index is built, so they cannot disagree with it.

## What review means

Before an entry is merged, someone has looked at the pinned package and
found that:

- its licence allows it to be passed on, and is the one its `package.json`
  names;
- what `uses` names is there: theme files and SVG pictures, inside the
  package's own folder;
- it is the publisher's own package, fetched from where they publish it.

A review says nothing of the extension's script. PiGit does not run it, so
nobody here reads it. What a script would have changed (an accent colour, a
folder's colour) is simply not there in PiGit.

## The index

`tools/registry.py build <folder>` fetches every pinned package, holds it
against its entry and writes:

- `index.json`: every entry with what was read from its package: the name,
  the licence, the repository, what it brings by name, what PiGit leaves out
  of it, and the pinned packages;
- `icons/<id>.png`: the extension's own picture.

On a push to `main` the workflow publishes that folder as the branch
`index`. PiGit reads `index.json` from there. It fetches a package from the
url its entry pins and installs it only when the bytes have the pinned size
and SHA-256, so the host of a package cannot change what is installed.

## Adding or updating an extension

1. Write or change its file under `extensions/`.
2. `python3 tools/registry.py check` reads every entry without fetching.
   `python3 tools/registry.py build /tmp/index` fetches and checks the
   packages too, as the workflow does on a pull request.
3. Open a pull request. It is merged after the review above.

The check refuses an entry whose package is not the pinned size or hash, is
another extension or version than the entry says, names no licence, holds a
link, or brings none of what `uses` names.

Needs Python 3.11 or later and nothing else.

## Not here yet

Language servers. An entry for a language will say how its server is
started; that part of the format is added with the PiGit release that reads
it.
