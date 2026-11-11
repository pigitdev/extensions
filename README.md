# PiGit extensions

The extensions PiGit has reviewed. Each entry pins one package in VS Code's
format by its SHA-256 and says what PiGit may use from it. PiGit's
Preferences › Extensions lists what is here and installs from it.

PiGit has no extension host. It reads an extension's colour themes and icon
themes as files and never loads its script. So an entry is a statement about
files: this package, with this hash, holds these themes. An entry for a
language server names one more file: the program PiGit may start.

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
| `uses` | What PiGit may use from the package: `colour-themes`, `icon-themes`, `interface-icons`, `language-server`. What a package brings beyond this is ignored. |
| `[package.any]` | The one package for every platform: where it is fetched from (https), its SHA-256 and its size in bytes. A package that differs by platform has `[package.linux-x64]`, `[package.darwin-arm64]` and so on in its place. |

The name a person reads, the licence, the repository, the themes by name and
the picture are not written here. They are read from the pinned package when
the index is built, so they cannot disagree with it.

## A language server

In VS Code an extension's script finds or downloads its server, picks the
build for the platform and composes the command. PiGit runs no script, so
the entry says those things in the script's place:

```toml
id = "rust-lang.rust-analyzer"
version = "0.3.3113"
summary = "The Rust language server: type hints, problems and completion in Rust files."
uses = ["language-server"]

[server]
id = "rust-analyzer"
language = "Rust"
grammars = ["rust"]
program = "server/rust-analyzer"
version = ["--version"]

[package.linux-x64]
url = "https://github.com/rust-lang/rust-analyzer/releases/download/2026-11-09/rust-analyzer-linux-x64.vsix"
sha256 = "c61de3efb461118516d4c523713baffca1fbdf8255e43fbb1a6c3dd709dab895"
size = 16947595

[package.darwin-arm64]
url = "https://github.com/rust-lang/rust-analyzer/releases/download/2026-11-09/rust-analyzer-darwin-arm64.vsix"
sha256 = "103be5b0ed1cc6b1f064fdf19ebe3914b6b66a58dbae2fb4d9e503f318cc44dd"
size = 15806448
```

| Key | What it is |
|---|---|
| `id` | The server's name as its own project writes it. Where PiGit ships a record of that name, the package is one more place a copy of that server is found, and PiGit's record says how it is started. |
| `language` | The language it serves, as a person names it. |
| `grammars` | The grammar ids or file endings of the files it reads, for a server PiGit ships no record of. |
| `program` | The server, as a path inside the package. It is the one file PiGit makes runnable, and the only one it starts. |
| `args` | What starts it speaking over its standard streams. Left out where it needs none. |
| `version` | What makes it print its version and leave. Left out for a server with no way to say it. |
| `runs` | One line on what it runs of the project's own to read it, where it does: a build, a script. PiGit shows it before the server is turned on. Left out where it runs nothing. |

`[server]` and `language-server` in `uses` go together: an entry has both or
neither. A server differs by platform, so its entry pins one package per
platform, and PiGit offers Install only where one is pinned for the
computer it runs on. The check holds every pinned package against the
entry: the program must be a file of each.

PiGit installs a server only from here. A package from Open VSX never
starts a program, whatever it holds. Installed, the server still starts
only when the person turns it on for a repository.

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

For an entry with `[server]` the review is of more, because PiGit starts
what it names:

- the package is the server project's own release, fetched from where that
  project publishes it, and the pinned version is a release it stands
  behind, not a nightly build;
- `program` is the server itself and nothing that wraps it;
- `args` and `version` are what the server's own documentation gives;
- `runs` says what the server runs of a project to read it, if anything.

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
link, brings none of what `uses` names, or does not hold the server its
`[server]` names.

Needs Python 3.11 or later and nothing else.

## Not here yet

A server that is a Node program, or one fetched apart from its extension's
package. An entry names a program the package itself holds, built for the
platform.
