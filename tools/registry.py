#!/usr/bin/env python3
"""Checks the registry's entries and builds the index PiGit reads.

    registry.py check              read every entry; fetch nothing
    registry.py build <folder>     fetch every package, hold it against its
                                   entry, and write <folder>/index.json and
                                   <folder>/icons/<id>.png

A package is data here. It is hashed, and its package.json and its picture
are read from the archive in memory. Nothing in it is unpacked or run.

Needs Python 3.11 or later and nothing else.
"""

import hashlib
import io
import json
import pathlib
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENTRIES = ROOT / "extensions"

# What PiGit may use from an extension, as an entry's `uses` names it, and
# the key of package.json each is declared under.
USES = {
    "colour-themes": ("contributes", "themes"),
    "icon-themes": ("contributes", "iconThemes"),
    "interface-icons": ("pigit", "interfaceIcons"),
}
# The one use package.json declares nothing for: the program the entry's
# own `[server]` names, which PiGit starts in the place of the extension's
# script.
SERVER = "language-server"
# What `[server]` may hold, and the most words it is started or asked with.
SERVER_KEYS = {"id", "language", "grammars", "program", "args", "version", "runs"}
MAX_WORDS = 32
# The platforms a package may be pinned for. `any` is one package for all.
PLATFORMS = {
    "any",
    "linux-x64",
    "linux-arm64",
    "darwin-x64",
    "darwin-arm64",
    "win32-x64",
    "win32-arm64",
}
# PiGit's own limits: a package it would refuse has no place here.
MAX_PACKAGE = 256 * 1024 * 1024
MAX_FILES = 50_000
MAX_MANIFEST = 4 * 1024 * 1024
MAX_ICON = 2 * 1024 * 1024
MAX_REDIRECTS = 3

PLAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Refused(Exception):
    """An entry or its package is not as the registry needs it."""


def plain(text):
    return isinstance(text, str) and bool(PLAIN.match(text))


def read_entry(path):
    """One entry, checked as far as its own text goes."""
    with open(path, "rb") as file:
        entry = tomllib.load(file)
    unknown = set(entry) - {"id", "version", "summary", "uses", "package", "server"}
    if unknown:
        raise Refused(f"it has keys the registry does not read: {sorted(unknown)}")
    ident = entry.get("id")
    if not isinstance(ident, str) or ident != ident.lower() or ident.count(".") < 1:
        raise Refused("`id` is `publisher.name`, in lower case")
    publisher, _, name = ident.partition(".")
    if not plain(publisher) or not plain(name):
        raise Refused("`id` holds a character a folder's name cannot")
    if path.name != f"{ident}.toml":
        raise Refused(f"the file is named after its id: {ident}.toml")
    if not plain(entry.get("version")):
        raise Refused("`version` is missing, or holds a character a folder's name cannot")
    summary = entry.get("summary")
    if not isinstance(summary, str) or not 0 < len(summary) <= 200 or "\n" in summary:
        raise Refused("`summary` is one line of at most 200 characters")
    uses = entry.get("uses")
    if not isinstance(uses, list) or not uses or len(set(uses)) != len(uses):
        raise Refused("`uses` lists what PiGit may use, each once")
    if not set(uses) <= set(USES) | {SERVER}:
        raise Refused(f"`uses` may hold {sorted(set(USES) | {SERVER})}")
    if ("server" in entry) != (SERVER in uses):
        raise Refused(f"`[server]` and `{SERVER}` in `uses` go together")
    if "server" in entry:
        entry["server"] = read_server(entry["server"])
    packages = entry.get("package")
    if not isinstance(packages, dict) or not packages:
        raise Refused("it pins no package")
    if not set(packages) <= PLATFORMS:
        raise Refused(f"a package is pinned for one of {sorted(PLATFORMS)}")
    if "any" in packages and len(packages) > 1:
        raise Refused("`any` is the one package for every platform")
    for platform, package in packages.items():
        if not isinstance(package, dict) or set(package) != {"url", "sha256", "size"}:
            raise Refused(f"package.{platform} holds exactly url, sha256 and size")
        url = urllib.parse.urlsplit(str(package["url"]))
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise Refused(f"package.{platform}: the url is https, with no user in it")
        if not isinstance(package["sha256"], str) or not SHA256.match(package["sha256"]):
            raise Refused(f"package.{platform}: sha256 is 64 lower-case hex digits")
        size = package["size"]
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_PACKAGE:
            raise Refused(f"package.{platform}: size is the package's bytes, at most {MAX_PACKAGE}")
    return entry


def read_server(server):
    """An entry's `[server]`, checked and with its program's path made plain."""
    if not isinstance(server, dict) or not set(server) <= SERVER_KEYS:
        raise Refused(f"`[server]` may hold {sorted(SERVER_KEYS)}")
    if not plain(server.get("id")):
        raise Refused("server.id is the server's own name, as a folder could be named")
    language = server.get("language")
    if not isinstance(language, str) or not language.strip() or "\n" in language:
        raise Refused("server.language is the language as a person names it")
    words = {}
    for key in ("grammars", "args", "version"):
        value = server.get(key, [])
        if (
            not isinstance(value, list)
            or len(value) > MAX_WORDS
            or not all(isinstance(word, str) and word for word in value)
        ):
            raise Refused(f"server.{key} is a list of at most {MAX_WORDS} words")
        words[key] = value
    if not words["grammars"]:
        raise Refused("server.grammars names the grammars or file endings it reads")
    program = inside(server.get("program", "")) if isinstance(server.get("program"), str) else None
    if program is None:
        raise Refused("server.program is a path inside the package")
    runs = server.get("runs")
    if runs is not None and (not isinstance(runs, str) or not 0 < len(runs) <= 200 or "\n" in runs):
        raise Refused("server.runs is one line of at most 200 characters")
    read = {"id": server["id"], "language": language.strip(), "program": program, **words}
    if runs is not None:
        read["runs"] = runs
    return read


class HttpsOnly(urllib.request.HTTPRedirectHandler):
    """Follows a few redirects, and none that leaves https."""

    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise Refused(f"the download was sent to a place that is not https: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, size):
    """The bytes at `url`, which must be exactly `size` of them."""
    opener = urllib.request.build_opener(HttpsOnly)
    request = urllib.request.Request(url, headers={"User-Agent": "pigit-extensions-registry"})
    try:
        with opener.open(request, timeout=120) as response:
            data = response.read(size + 1)
    except urllib.error.URLError as error:
        raise Refused(f"the package could not be fetched: {error}") from error
    if len(data) != size:
        raise Refused(f"the package is not the {size} bytes its entry says")
    return data


def inside(named):
    """A path a manifest names, kept only when it stays in its folder."""
    parts = []
    for part in pathlib.PurePosixPath(str(named).replace("\\", "/")).parts:
        if part == ".":
            continue
        if part in ("..", "/") or part.startswith("/"):
            return None
        parts.append(part)
    return "/".join(parts) if parts else None


def text(value, words):
    """A label, looked up where it is written as `%key%`."""
    if not isinstance(value, str):
        return None
    if value.startswith("%") and value.endswith("%") and len(value) > 2:
        found = words.get(value[1:-1])
        if isinstance(found, dict):
            found = found.get("message")
        if isinstance(found, str):
            return found
    return value


def read_package(entry, data, platform):
    """What a package holds, held against its entry. Reads the archive in
    memory: its manifest, the labels beside it and its picture."""
    package = entry["package"][platform]
    digest = hashlib.sha256(data).hexdigest()
    if digest != package["sha256"]:
        raise Refused(f"package.{platform}: its SHA-256 is {digest}, not the one pinned")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise Refused(f"package.{platform} is no .vsix: {error}") from error
    files = {info.filename: info for info in archive.infolist()}
    if len(files) > MAX_FILES:
        raise Refused(f"package.{platform} holds more than {MAX_FILES} files")
    for info in files.values():
        # the file type is in the high bits of a Unix entry's attributes
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise Refused(f"package.{platform} holds a link: {info.filename}")

    def read(name, most):
        info = files.get(f"extension/{name}")
        if info is None or info.is_dir() or info.file_size > most:
            return None
        return archive.read(info)

    raw = read("package.json", MAX_MANIFEST)
    if raw is None:
        raise Refused(f"package.{platform} has no extension/package.json PiGit would read")
    manifest = json.loads(raw)
    words_raw = read("package.nls.json", MAX_MANIFEST)
    words = json.loads(words_raw) if words_raw else {}
    ident = f"{manifest.get('publisher')}.{manifest.get('name')}".lower()
    if ident != entry["id"]:
        raise Refused(f"package.{platform} is {ident}, not {entry['id']}")
    if manifest.get("version") != entry["version"]:
        raise Refused(f"package.{platform} is version {manifest.get('version')}, not {entry['version']}")
    licence = manifest.get("license")
    if not isinstance(licence, str) or not licence.strip():
        raise Refused(f"package.{platform} names no licence")

    brings = {}
    for use, (group, key) in USES.items():
        declared = (manifest.get(group) or {}).get(key) or []
        kept = []
        for item in declared:
            path = inside(item.get("path", ""))
            if path is None or f"extension/{path}" not in files:
                continue
            label = text(item.get("label"), words) or item.get("id") or path
            if use == "colour-themes":
                light = item.get("uiTheme") in ("vs", "hc-light")
                kept.append({"label": label, "base": "light" if light else "dark"})
            else:
                kept.append({"id": item.get("id"), "label": label})
        if use in entry["uses"]:
            if not kept:
                raise Refused(f"`uses` names {use}, and package.{platform} brings none")
            brings[use] = kept
    server = entry.get("server")
    if server is not None:
        # the program is a plain file of this platform's package: PiGit makes
        # that one file runnable and starts nothing else
        info = files.get(f"extension/{server['program']}")
        if info is None or info.is_dir() or info.file_size == 0:
            raise Refused(f"package.{platform} does not hold the server at {server['program']}")
    contributes = manifest.get("contributes") or {}
    left_out = {
        "script": "main" in manifest or "browser" in manifest,
        "settings": "configuration" in contributes,
        "commands": len(contributes.get("commands") or []),
        "grammars": len(contributes.get("grammars") or []),
        "fontIcons": len(contributes.get("productIconThemes") or []),
    }
    icon = None
    icon_path = inside(manifest.get("icon", "")) if manifest.get("icon") else None
    if icon_path and icon_path.lower().endswith(".png"):
        icon = read(icon_path, MAX_ICON)
    repository = manifest.get("repository")
    if isinstance(repository, dict):
        repository = repository.get("url")
    return {
        "id": entry["id"],
        "publisher": manifest["publisher"],
        "name": manifest["name"],
        "version": entry["version"],
        "displayName": text(manifest.get("displayName"), words) or manifest["name"],
        "summary": entry["summary"],
        "licence": licence.strip(),
        "repository": repository if isinstance(repository, str) else None,
        "uses": entry["uses"],
        "brings": brings,
        "leftOut": left_out,
        **({"server": server} if server is not None else {}),
    }, icon


def entries():
    found, failed = [], False
    for path in sorted(ENTRIES.glob("*.toml")):
        try:
            found.append(read_entry(path))
        except (Refused, tomllib.TOMLDecodeError) as why:
            print(f"{path.name}: {why}", file=sys.stderr)
            failed = True
    return found, failed


def build(out):
    found, failed = entries()
    out.mkdir(parents=True, exist_ok=True)
    (out / "icons").mkdir(exist_ok=True)
    listed = []
    for entry in found:
        try:
            described = None
            for platform, package in sorted(entry["package"].items()):
                data = fetch(package["url"], package["size"])
                one, icon = read_package(entry, data, platform)
                # every platform's package is the same extension: what the
                # first says of it stands for all
                if described is None:
                    described = one
                    if icon:
                        (out / "icons" / f"{entry['id']}.png").write_bytes(icon)
                        described["icon"] = f"icons/{entry['id']}.png"
                    else:
                        described["icon"] = None
            described["packages"] = entry["package"]
            listed.append(described)
            print(f"{entry['id']} {entry['version']}: checked")
        except (Refused, json.JSONDecodeError, KeyError) as why:
            print(f"{entry['id']}: {why}", file=sys.stderr)
            failed = True
    index = {"format": 1, "extensions": listed}
    (out / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return failed


def main(args):
    if args == ["check"]:
        found, failed = entries()
        print(f"{len(found)} entries read")
        return 1 if failed else 0
    if len(args) == 2 and args[0] == "build":
        return 1 if build(pathlib.Path(args[1])) else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
