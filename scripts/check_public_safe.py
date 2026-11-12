#!/usr/bin/env python3
"""Scan the repo and git history for things that should not be published.

Looks through tracked files, untracked files that are not gitignored, every
commit's file contents, and commit messages. Git author lines are not scanned:
they are the local git identity, not project content.

Gitignored local settings, brand, templates and run history are skipped so a
private ABR GUID in my-settings.toml is not treated as a published leak.
Do not commit that file.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BINARY_SUFFIXES = {
    ".png",
    ".gif",
    ".jpg",
    ".jpeg",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".woff",
    ".woff2",
}

# Common given names and surnames. A hit needs one of each, in that order.
FIRST_NAMES = {
    "james", "john", "robert", "michael", "william", "david", "richard", "joseph",
    "thomas", "charles", "christopher", "daniel", "matthew", "anthony", "donald",
    "steven", "paul", "andrew", "joshua", "kenneth", "kevin", "brian", "george",
    "timothy", "ronald", "edward", "jason", "jeffrey", "ryan", "jacob", "gary",
    "nicholas", "eric", "jonathan", "stephen", "larry", "justin", "scott",
    "brandon", "benjamin", "samuel", "raymond", "gregory", "alexander", "patrick",
    "jack", "dennis", "jerry", "tyler", "aaron", "adam", "nathan", "henry",
    "peter", "douglas", "noah", "ethan", "jeremy", "walter", "christian", "keith",
    "roger", "terry", "austin", "sean", "gerald", "carl", "dylan", "jesse",
    "jordan", "bryan", "billy", "bruce", "gabriel", "logan", "albert", "alan",
    "wayne", "elijah", "randy", "vincent", "philip", "harry", "ralph", "mary",
    "patricia", "jennifer", "linda", "elizabeth", "barbara", "susan", "jessica",
    "sarah", "karen", "nancy", "lisa", "margaret", "betty", "sandra", "ashley",
    "kimberly", "emily", "donna", "michelle", "dorothy", "carol", "amanda",
    "melissa", "deborah", "stephanie", "rebecca", "sharon", "laura", "cynthia",
    "kathleen", "amy", "angela", "shirley", "anna", "brenda", "pamela", "emma",
    "nicole", "helen", "samantha", "katherine", "christine", "debra", "rachel",
    "catherine", "carolyn", "janet", "ruth", "maria", "heather", "diane", "olivia",
    "julie", "joyce", "victoria", "kelly", "christina", "joan", "evelyn", "judith",
    "andrea", "hannah", "megan", "cheryl", "jacqueline", "martha", "gloria",
    "teresa", "ann", "sara", "madison", "frances", "kathryn", "janice", "jean",
    "abigail", "alice", "julia", "judy", "sophia", "grace", "denise", "amber",
    "doris", "marilyn", "danielle", "beverly", "isabella", "theresa", "diana",
    "natalie", "brittany", "charlotte", "marie", "kayla", "alexis", "lori",
}
SURNAMES = {
    "smith", "jones", "williams", "brown", "wilson", "taylor", "johnson", "white",
    "martin", "anderson", "thompson", "nguyen", "thomas", "walker", "harris",
    "lee", "robinson", "kelly", "king", "wright", "scott", "green", "baker",
    "adams", "nelson", "hill", "ramirez", "campbell", "mitchell", "roberts",
    "carter", "phillips", "evans", "turner", "torres", "parker", "collins",
    "edwards", "stewart", "flores", "morris", "murphy", "cook", "rogers",
    "morgan", "peterson", "cooper", "reed", "bailey", "bell", "gomez", "wood",
    "bennett", "gray", "watson", "brooks", "sanders", "price", "bennett",
    "wood", "ross", "griffin", "hayes", "myers", "ford", "hamilton", "graham",
    "sullivan", "wallace", "woods", "cole", "west", "jordan", "owens", "reynolds",
    "fisher", "ellis", "harrison", "gibson", "mcdonald", "cruz", "marshall",
    "ortiz", "gomez", "murray", "freeman", "wells", "webb", "simpson", "stevens",
    "tucker", "porter", "hunter", "hicks", "crawford", "henry", "boyd", "mason",
    "morales", "kennedy", "warren", "dixon", "ramos", "reyes", "burns", "gordon",
    "shaw", "holmes", "rice", "robertson", "hunt", "black", "daniels", "palmer",
    "mills", "nichols", "grant", "knight", "ferguson", "rose", "stone", "hawkins",
    "dunn", "perkins", "hudson", "spencer", "gardner", "stephens", "payne",
    "pierce", "berry", "matthews", "arnold", "wagner", "willis", "ray", "watkins",
    "olson", "carroll", "duncan", "snyder", "hart", "cunningham", "bradley",
    "lane", "andrews", "ruiz", "harper", "fox", "riley", "armstrong", "carpenter",
    "weaver", "greene", "lawrence", "elliott", "chavez", "sims", "austin",
    "peters", "kelley", "franklin", "lawson", "fields", "gutierrez", "ryan",
    "schmidt", "carr", "vasquez", "castillo", "wheeler", "chapman", "oliver",
    "montgomery", "richards", "williamson", "johnston", "banks", "meyer",
    "bishop", "mccoy", "howell", "alvarez", "morrison", "hansen", "fernandez",
    "garza", "harvey", "little", "burton", "stanley", "nguyen", "george",
    "jacobs", "reid", "kim", "fuller", "lynch", "dean", "gilbert", "garrett",
    "romero", "welch", "larson", "frazier", "burke", "hanson", "day", "mendoza",
    "moreno", "bowman", "medina", "fowler", "brewer", "hoffman", "carlson",
    "silva", "pearson", "holland", "douglas", "fleming", "jensen", "vargas",
    "byrd", "davidson", "hopkins", "may", "terry", "herrera", "wade", "soto",
    "walters", "curtis", "neal", "caldwell", "lowe", "jennings", "barnett",
    "graves", "jimenez", "horton", "shelton", "barrett", "obrien", "castro",
    "sutton", "gregory", "mckinney", "lucas", "miles", "craig", "rodriquez",
    "chambers", "holt", "lambert", "fletcher", "watts", "bates", "hale",
    "rhodes", "pena", "beck", "newman", "haynes", "mcdaniel", "mendez", "bush",
    "vaughn", "parks", "dawson", "santiago", "norris", "hardy", "love", "steele",
    "curry", "powers", "schultz", "barker", "guzman", "page", "munoz", "ball",
    "keller", "chandler", "weber",
}


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    line: int
    excerpt: str


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    return scan(root)


def scan(root: Path) -> int:
    findings: list[Finding] = []
    files = list(_worktree_files(root))
    for path in files:
        text = _read_text(path)
        if text is None:
            continue
        findings.extend(_with_path(path.relative_to(root).as_posix(), text))
    commits = _commits(root)
    for commit in commits:
        message = _git(root, "log", "-1", "--format=%B", commit)
        findings.extend(_with_path(f"{commit[:10]}:message", message))
        listed = _git(root, "ls-tree", "-r", "--name-only", commit)
        for name in listed.splitlines():
            if _binary_name(name):
                continue
            blob = _git_bytes(root, "show", f"{commit}:{name}")
            if blob is None or b"\0" in blob:
                continue
            text = blob.decode("utf-8", "replace")
            findings.extend(_with_path(f"{commit[:10]}:{name}", text))
    unique = _unique(findings)
    print("bas-gst-check public scan")
    print(f"files: {len(files)}")
    print(f"commits: {len(commits)}")
    print(f"findings: {len(unique)}")
    for finding in unique:
        print(f"{finding.kind}\t{finding.path}\t{finding.line}\t{finding.excerpt}")
    return 1 if unique else 0


def find_in_text(text: str) -> list[tuple[str, int, str]]:
    """Return (kind, line_number, excerpt) hits in one text."""
    hits: list[tuple[str, int, str]] = []
    patterns = _patterns()
    for line_number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            if kind == "abn" and not _abn_checksum(match.group(0)):
                continue
            if kind == "name" and not _name_hit(match.group(0)):
                continue
            excerpt = line.strip()
            if len(excerpt) > 120:
                excerpt = excerpt[:117] + "..."
            hits.append((kind, line_number, excerpt))
            break
    return hits


def _patterns() -> list[tuple[str, re.Pattern[str]]]:
    email = re.compile(
        r"[A-Za-z0-9._%+\-]+@" + r"[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
    )
    mobile = re.compile(r"\b(?:\+?61[\s\-]?|0)4\d{2}[\s\-]?\d{3}[\s\-]?\d{3}\b")
    landline = re.compile(r"\b0[2378][\s\-]?\d{4}[\s\-]?\d{4}\b")
    abn = re.compile(r"\b\d{11}\b|\b\d{2}\s\d{3}\s\d{3}\s\d{3}\b")
    users = "/" + "Users" + "/"
    home = "/" + "home" + "/"
    windows = re.escape("C:" + "\\" + "Users" + "\\")
    path = re.compile(rf"{re.escape(users)}|{re.escape(home)}|{windows}")
    private_key = "-----BEGIN " + "PRIVATE KEY-----"
    name = re.compile(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b")
    guid = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    secrets = [
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(re.escape(private_key)),
        re.compile(r"ghp_[A-Za-z0-9]{20,}"),
        re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"\bpassword\s*[:=]\s*['\"][^'\"]{6,}['\"]", re.IGNORECASE),
        re.compile(r"\bapi[_-]?key\s*[:=]\s*['\"][^'\"]{6,}['\"]", re.IGNORECASE),
    ]
    return [
        ("email", email),
        ("phone", mobile),
        ("phone", landline),
        ("abn", abn),
        ("path", path),
        *[("secret", pattern) for pattern in secrets],
        ("guid", guid),
        ("name", name),
    ]


def _abn_checksum(raw: str) -> bool:
    digits = [int(character) for character in re.sub(r"\D", "", raw)]
    if len(digits) != 11:
        return False
    digits[0] -= 1
    if digits[0] < 0:
        return False
    weights = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
    return sum(digit * weight for digit, weight in zip(digits, weights)) % 89 == 0


def _name_hit(raw: str) -> bool:
    first, last = raw.split()
    return first.casefold() in FIRST_NAMES and last.casefold() in SURNAMES


def _with_path(path: str, text: str) -> list[Finding]:
    return [
        Finding(kind, path, line, excerpt)
        for kind, line, excerpt in find_in_text(text)
    ]


def _unique(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str, int, str]] = set()
    ordered: list[Finding] = []
    for finding in findings:
        key = (finding.kind, finding.path, finding.line, finding.excerpt)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(finding)
    return ordered


def _worktree_files(root: Path) -> list[Path]:
    listed = _git(root, "ls-files", "-c", "-o", "--exclude-standard")
    paths = []
    for name in listed.splitlines():
        path = root / name
        if path.is_file() and not _binary_name(name):
            paths.append(path)
    return paths


def _commits(root: Path) -> list[str]:
    output = _git(root, "rev-list", "--all")
    return [line for line in output.splitlines() if line]


def _read_text(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\0" in data:
        return None
    return data.decode("utf-8", "replace")


def _binary_name(name: str) -> bool:
    return Path(name).suffix.lower() in BINARY_SUFFIXES


def _git(root: Path, *args: str) -> str:
    blob = _git_bytes(root, *args)
    if blob is None:
        return ""
    return blob.decode("utf-8", "replace")


def _git_bytes(root: Path, *args: str) -> bytes | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout


if __name__ == "__main__":
    raise SystemExit(main())
