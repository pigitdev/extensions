#!/usr/bin/env python3
"""Tests of the registry's checks. They build their packages in memory and
fetch nothing: `python3 tools/test_registry.py`."""

import hashlib
import io
import json
import pathlib
import stat
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import registry  # noqa: E402

MANIFEST = {
    "publisher": "Someone",
    "name": "night",
    "version": "1.2.0",
    "displayName": "%name%",
    "license": "MIT",
    "icon": "icon.png",
    "main": "./dist/main.js",
    "repository": {"type": "git", "url": "https://example.com/someone/night"},
    "contributes": {
        "themes": [
            {"label": "Night", "uiTheme": "vs-dark", "path": "./themes/night.json"},
            {"label": "Day", "uiTheme": "vs", "path": "themes/day.json"},
            {"label": "Gone", "uiTheme": "vs", "path": "./themes/gone.json"},
            {"label": "Outside", "uiTheme": "vs", "path": "../outside.json"},
        ],
        "configuration": {"title": "Night"},
        "commands": [{"command": "night.reset", "title": "Reset"}],
    },
}


def package(manifest=None, extra=(), link=None):
    """A .vsix in memory, and the entry that pins it."""
    held = io.BytesIO()
    with zipfile.ZipFile(held, "w") as archive:
        archive.writestr("extension/package.json", json.dumps(manifest or MANIFEST))
        archive.writestr("extension/package.nls.json", json.dumps({"name": "Night Themes"}))
        archive.writestr("extension/themes/night.json", "{}")
        archive.writestr("extension/themes/day.json", "{}")
        archive.writestr("extension/icon.png", b"\x89PNG")
        for name, content in extra:
            archive.writestr(name, content)
        if link:
            info = zipfile.ZipInfo(link)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/etc/hostname")
    data = held.getvalue()
    entry = {
        "id": "someone.night",
        "version": "1.2.0",
        "summary": "Two themes.",
        "uses": ["colour-themes"],
        "package": {
            "any": {
                "url": "https://example.com/night.vsix",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        },
    }
    return entry, data


class Entries(unittest.TestCase):
    def write(self, name, text):
        folder = pathlib.Path(tempfile.mkdtemp())
        path = folder / name
        path.write_text(text, encoding="utf-8")
        return path

    GOOD = (
        'id = "someone.night"\nversion = "1.2.0"\nsummary = "Two themes."\n'
        'uses = ["colour-themes"]\n[package.any]\nurl = "https://example.com/night.vsix"\n'
        f'sha256 = "{"a" * 64}"\nsize = 10\n'
    )

    def test_an_entry_that_is_whole_is_read(self):
        entry = registry.read_entry(self.write("someone.night.toml", self.GOOD))
        self.assertEqual(entry["uses"], ["colour-themes"])

    def test_an_entry_is_refused_for_what_it_gets_wrong(self):
        for changed, why in [
            (self.GOOD.replace("https://", "http://"), "https"),
            (self.GOOD.replace("https://", "https://user:key@"), "no user"),
            (self.GOOD.replace('"a' , '"A'), "hex"),
            (self.GOOD.replace("size = 10", "size = 0"), "size"),
            (self.GOOD.replace("colour-themes", "scripts"), "may hold"),
            # a server and the use that lets PiGit start it go together
            (self.GOOD.replace('["colour-themes"]', '["language-server"]'), "go together"),
            (self.GOOD + '[server]\nid = "x"\n', "go together"),
            (self.GOOD.replace("someone.night", "Someone.night"), "lower case"),
            (self.GOOD.replace("[package.any]", "[package.amiga]"), "pinned for"),
            (self.GOOD + 'extra = "x"\n', "exactly"),
            (self.GOOD.replace('summary = "Two themes."', 'summary = ""'), "summary"),
        ]:
            with self.assertRaises(registry.Refused, msg=why) as refused:
                registry.read_entry(self.write("someone.night.toml", changed))
            self.assertIn(why, str(refused.exception))
        # the file is named after the extension it pins
        with self.assertRaises(registry.Refused):
            registry.read_entry(self.write("other.toml", self.GOOD))


    SERVING = GOOD.replace('["colour-themes"]', '["language-server"]') + (
        '[server]\nid = "lang-server"\nlanguage = "Lang"\ngrammars = ["lang"]\n'
        'program = "./server/lang-server"\nversion = ["--version"]\n'
    )

    def test_an_entry_names_the_one_program_pigit_may_start(self):
        entry = registry.read_entry(self.write("someone.night.toml", self.SERVING))
        self.assertEqual(
            entry["server"],
            {
                "id": "lang-server",
                "language": "Lang",
                "program": "server/lang-server",
                "grammars": ["lang"],
                "args": [],
                "version": ["--version"],
            },
        )

    def test_a_server_is_refused_for_what_it_gets_wrong(self):
        for changed, why in [
            (self.SERVING.replace("./server/lang-server", "../../bin/sh"), "inside the package"),
            (self.SERVING.replace("./server/lang-server", "/bin/sh"), "inside the package"),
            (self.SERVING.replace('program = "./server/lang-server"\n', ""), "inside the package"),
            (self.SERVING.replace('id = "lang-server"', 'id = "../x"'), "server.id"),
            (self.SERVING.replace('language = "Lang"', 'language = " "'), "server.language"),
            (self.SERVING.replace('grammars = ["lang"]', "grammars = []"), "server.grammars"),
            (self.SERVING.replace('["--version"]', '"--version"'), "server.version"),
            (self.SERVING + "args = [1]\n", "server.args"),
            (self.SERVING + 'script = "./out/main.js"\n', "may hold"),
            (self.SERVING + 'runs = ""\n', "server.runs"),
        ]:
            with self.assertRaises(registry.Refused, msg=why) as refused:
                registry.read_entry(self.write("someone.night.toml", changed))
            self.assertIn(why, str(refused.exception))


class Packages(unittest.TestCase):
    def test_a_package_says_what_it_brings_and_what_is_left_out(self):
        entry, data = package()
        described, icon = registry.read_package(entry, data, "any")
        self.assertEqual(described["displayName"], "Night Themes")
        self.assertEqual(described["licence"], "MIT")
        self.assertEqual(described["repository"], "https://example.com/someone/night")
        # a theme whose file is not there, or is named outside, is not brought
        self.assertEqual(
            described["brings"],
            {"colour-themes": [{"label": "Night", "base": "dark"}, {"label": "Day", "base": "light"}]},
        )
        self.assertEqual(
            described["leftOut"],
            {"script": True, "settings": True, "commands": 1, "grammars": 0, "fontIcons": 0},
        )
        self.assertEqual(icon, b"\x89PNG")

    def test_a_package_that_is_not_the_one_pinned_is_refused(self):
        entry, data = package()
        with self.assertRaisesRegex(registry.Refused, "SHA-256"):
            registry.read_package(entry, data + b"x", "any")
        for key, value, why in [
            ("version", "1.3.0", "version"),
            ("id", "someone.other", "not someone.other"),
            ("uses", ["icon-themes"], "brings none"),
        ]:
            other = dict(entry, **{key: value})
            with self.assertRaisesRegex(registry.Refused, why):
                registry.read_package(other, data, "any")

    def test_a_package_with_a_link_or_without_a_licence_is_refused(self):
        entry, data = package(link="extension/themes/host.json")
        with self.assertRaisesRegex(registry.Refused, "link"):
            registry.read_package(entry, data, "any")
        bare = {key: value for key, value in MANIFEST.items() if key != "license"}
        entry, data = package(manifest=bare)
        with self.assertRaisesRegex(registry.Refused, "licence"):
            registry.read_package(entry, data, "any")

    def test_a_server_must_be_a_file_of_every_package_pinned(self):
        server = {
            "id": "lang-server",
            "language": "Lang",
            "program": "server/lang-server",
            "grammars": ["lang"],
            "args": [],
            "version": ["--version"],
        }
        entry, data = package(extra=[("extension/server/lang-server", b"\x7fELF")])
        entry = dict(entry, uses=["language-server"], server=server)
        described, _ = registry.read_package(entry, data, "any")
        # it brings no theme that PiGit uses, and the index says what is started
        self.assertEqual(described["brings"], {})
        self.assertEqual(described["server"], server)
        self.assertEqual(described["uses"], ["language-server"])
        # a package without the program, with a folder in its place, or with
        # an empty file there, is refused
        for extra in ([], [("extension/server/lang-server/", b"")], [("extension/server/lang-server", b"")]):
            other, data = package(extra=extra)
            other = dict(other, uses=["language-server"], server=server)
            with self.assertRaisesRegex(registry.Refused, "does not hold the server"):
                registry.read_package(other, data, "any")

    def test_a_path_stays_inside_its_folder(self):
        self.assertEqual(registry.inside("./themes/a.json"), "themes/a.json")
        self.assertEqual(registry.inside("themes\\a.json"), "themes/a.json")
        self.assertIsNone(registry.inside("../a.json"))
        self.assertIsNone(registry.inside("/etc/hostname"))
        self.assertIsNone(registry.inside("themes/../../a.json"))


if __name__ == "__main__":
    unittest.main()
