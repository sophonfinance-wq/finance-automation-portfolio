"""Confidentiality linter — deny-list sweep over every published surface.

This portfolio repository is public, so it carries a deny list of terms
that must never appear on any published surface. The list is stored as
**one-way SHA-256 digests**: the plaintext terms do not exist anywhere in
this repository and cannot be recovered from the digests. Scanning works
by normalizing each surface into a token stream, hashing every candidate
word n-gram, and testing membership against the digest set — so matching
stays case-insensitive and boundary-aware without ever materializing a
denied term.

A failure reports the digest (and surface) only. It never prints the
matched text, so a leak is pinpointed without being republished in CI
logs.

Surfaces swept:

* ``atlas_data.py``  — the data model source
* ``generate.py``    — the renderer source
* ``README.md``      — the system documentation
* ``artifact-html``  — the committed generated artifact
* ``tree-sweep``     — every text file under ``finance-atlas/``
* ``repo-sweep``     — every text file in the repository
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

from atlas_tests.conftest import ARTIFACT_PATH, ATLAS_DIR, README_PATH

REPO_DIR = ATLAS_DIR.parent

# ---------------------------------------------------------------------------
# The deny list: (sha256 hex digest of the normalized term, words in term).
# Normalization: fold typographic quotes, lowercase, tokenize on
# [0-9a-z]+(?:'[0-9a-z]+)* and join with single spaces (see _normalize_term).
# ---------------------------------------------------------------------------

DENYLIST: Tuple[Tuple[str, int], ...] = (
    ("4b51869a0a0a337a2ee1c026f34c0047a1a920e31bf2aa21e2cfbf6162bbf88c", 1),
    ("104f24e15f4dba76498bb256593dc6d95876d881ee2201ff369225b6d51e8b45", 1),
    ("c68960d286ef20dff5517126fac818e6f84679dac7d57fa45e0592c0b4c4098a", 1),
    ("0ff835429838c0eb60d1355824fa0dacb1d442181f1144a2222c0f14787dbd82", 1),
    ("b949562cfbbb8a3f77822e1dd014c7a5ad0c41d678a7b077c8f2e2603deea118", 1),
    ("d20b5552e76dc110306b7e7a6ba9f4d687e79be4499c53100b857e03acb27bcd", 1),
    ("6e19168d4ccc4c65aef4ebcaeb7077d22bdd188ada1bd009cefdccdd0bab5314", 2),
    ("ef762732bdfdc7f9e98203168cde6d4d8497be5634af951cfc5d77095782376a", 1),
    ("317de6b75c673b9f0be5ba921055c8ba5557af9be6c0416200bfefb47f136f0b", 1),
    ("93056e3887baada689b5e83cf536fddbccd4d02f30544a64bcafbd634c087b3f", 2),
    ("c1ff7361fd458d09bd33330d16083f09817f5c16b92d100a5420a88d723e0a03", 2),
    ("3259138318d8d440dc78dd1fda6e1d67e418a87d1cd4720cb9b3b50c7b8c28ae", 1),
    ("485f92193f609d8554e24c2cf6799e5f165d86f51444b3cb8af427a5605db3d8", 1),
    ("4276bcf5bce056df19a486c98626d280e3369acb938d1ec12692ba0be9c094b0", 1),
    ("24c0b5b0d25a1dbc53b782135f6d059cb3b98172bdc83b0f13e9255340590627", 2),
    ("07d0adde2cb5c0786e1b9c6acfb3afedcadbf8d7b6b6d98e0a75f8c15c4e17be", 1),
    ("3b269f6605e1ac503805ffcbd3d1d04c2699bb0461475aa396bcd102cf1febb5", 1),
    ("a9379355097d37848ddb1064660158f9c1c84faefb44b713974294393ab0e34d", 1),
    ("23ff605cc0ed6a046dcc1395abddd9f3c75f3daa0dc09db67e9b909fd89f63c9", 1),
    ("192af3f87d67ca27b1afd556e5a5684b450fdad66f0447a3defd44625711ad93", 2),
    ("0665a716c250e9a57e709be63cb444115cb6998e8d164277e01e405919d93e2e", 2),
    ("568cee09d836ce4133de327578f4c3d08b45cb4cb37a1aad17bc52816045e162", 2),
    ("0e2e647c671bf09ec1a42a43c6bcf53a1878e83c5b1ec702b6a8f0dfa994bcad", 1),
    ("f224bd51c5721b8655ea3be077389f9f550dcc476be9c7c5783b051760e72f94", 2),
    ("1a82fbe34666630666c23b15cf850b511cf735aebd97f8c35662d40a8ea74510", 2),
    ("1ea2d8f8a54b1b5e93319fe2832c827d16b1bdc78211e05f2b3c9824196bc075", 1),
    ("aa75a3c045136bee296fb82fddc1ba96b23d444bae31b613617e79a6e87a6fbd", 2),
    ("685d57d9d210f52cad3de9f52cf2399e019da8f4cf408810ec096ae075408f51", 3),
    ("3713a14b74db31bd26780e137a7236064ee5cbeed886a78ed22b48ff5a7ada3a", 2),
    ("9cf0982d8a9906d2e43f0eb12d90748ed143308014d8a30196a8f23a3f99a6a6", 2),
    ("14e2e63674dc41b0b750c3e933304f8e3b811fc10626159ff3240a8b27235cff", 2),
    ("3db82f1cf8bc1da10e37e9070931ffbe8148068b25518a29449089f7dece92fc", 2),
    ("717991a9057aa1c391a93543e62643990168f3336975d85e3fc52552065181f4", 2),
    ("649409144dca81b65d6f7b390599e0b6c606b9f5c6b8ff2d633a88e76b5e6fed", 2),
    ("b4a47cf716af9c94c69482c4e947383ed440f01c77d349672e843a6932295e77", 2),
    ("6657c41ef56315fb8cfd05c6243d4143f02e2c8ef89f19af67b10ee75c519af8", 2),
    ("ed9cbe0121b9863bf670bcf29fad3d729744a7a573db9d2b175f78a881c7b885", 2),
    ("5602928aea15639d70e9fe4e55572b50d674c1096881c9a69b7207dac421b122", 2),
    ("205d2186665aa17240dca909893afa936556bdfd08f92e6c23707fe488b62c68", 2),
    ("5efd476510d9df4a080ab9d8e525d7150a974fec1d4bb12dfe0fec3b345035ae", 3),
    ("577d613ef51246e4545c3304a6f88edfde4fbbd070a26c35bf63671c05203a34", 2),
    ("847686f6127d614b32ce0eaf967330d8c9ea970958b58afd2370a67e11714713", 1),
    ("658b866f4c170619c7eab2167fe0e195ee8e0b4e80bba976068ca0270a81872b", 1),
    ("8ae29892fd981469ffb5a5a8a3fb439fec711ff6c64e3d63e568a38c350cde95", 1),
    ("9beadf10d0a349fee1cec85ac04087d89418dea0cdb9d5a5336ba808deeda2f6", 1),
    ("302ab6c6a1d9ca5c91276344043e201e0d1d30e548abdafacfbe09bea4870b64", 1),
    ("ef4b3693227a925818fe240687b68da126c567ef803eb8049783b8b29f8c9b87", 1),
    ("7350c38c5c1fb895b6a2394d5857e3d559835011c3c22e7d99424b0669d0f828", 1),
    ("f91ee2b5ecdfd10854df799dbaca9c696394487312b10ff5684aeed2e274cfa0", 1),
    ("acc3d05a9e26fce50e3e27ade96f2c7dfb6e6ff5bb92fd523e7350c97883f276", 3),
    ("243c06e44a9ea68e6f134eb3258e45e2eab8f520312f9deb7a62b30bc0308fa0", 1),
    ("930dddabae3845d2311d92aa987df61696b7d1d5f188c1df72a01de9dbdcd010", 1),
    ("7a2cb195b3ac8da527bb2bc78855698002386d2ac03fa4aa56c0d3016e1b983d", 2),
    ("ac99c3913702c9c14d1704859bc7ea6ff94f008f376c6c73c33baf83d54151b1", 1),
    ("38ab2e3a40b730b492fcedfd02d1058ee318b1d252593956aa4d40371bb633cb", 1),
    ("5d6005d3c8c5ce1af3b9647336f00f7a639538131f0496e8639ae337941c0e32", 1),
    ("607249f7575ba049fe50e3d35fc9136210d46e218c3626497261d230049195cb", 1),
    ("c50829408b9c3493b9ec44e649c871f8b380fa20af31795272ade4464a5fff6f", 1),
    ("1ff3f824a5d4fbbe4fc71235d354490a5c9575445db11110b890d60222e1511a", 1),
    ("e8d8550b00ff78c3d2b9e2c92988c705c19685de4db2f78a3f7dd95989c9b7c5", 1),
    ("fff045f2575092eee58374e6b24e2c3efae8533ac17811cf15939d4fd09a5284", 1),
    ("936bd937eaaa5eee9f68ba57909145e4569afd55562affe8d3ef59c5fcf16078", 1),
    ("8f9d5c63d365536095b33d60a64cb90449d232b2eee184629253b860cc65be39", 1),
    ("0ec14e62e17e8ea53f05dd24cc912bb11888c574cc206d28020c4803755544c2", 1),
    ("3a72c8e8fec7c5b7efd55cdc0946f7684258d41a07b2ffdf070b31ee4bb19b02", 2),
    ("f39ae6b82c3c2ce2e50b78e49427e3d38650fcfd537e824c1fa8152493760fc9", 1),
    ("f01289096de532bf802169285d07436f2d264918bc1d35da49a8612c5a9297ad", 2),
    ("c3a9b82d44e16c34a3cf9b9cbddd17a5608900a4dddee809bbcf38d4491cf438", 1),
    ("e24dab8434fe91a5fb227484178a161ea49b41d96e381ee146c085fc1c65178b", 2),
    ("9d00836eb5a5681f577f3f4e21e30d452b6bd9b5dc34c0647fe5db5748d598c6", 2),
    ("c31ec41e096db8309910f0532d7d262488032a4dcd21004ca2ce52162c04ce11", 3),
    ("8cecd2be71be971cf5ff0b9c1be6c119ad5647d836fe34a63f96d3b6e8aa9136", 2),
    ("0ff37cd45207c8bf2c058951e08146cb734209e2eefcd6f9cc6542e94dcd99f8", 2),
    ("a57d3c0d80ab62c385594e92c7051034768a7c77157fd5a961b1784ceeb36e8e", 2),
    ("d31145194353f0d6aa8b7e37c695d13315dfa5900939456cba9251178d888782", 2),
    ("aca0b9d95e4fae404ed50d7062ac4ff1f987fc158371e01344eb55f3471f7bd9", 1),
    ("e74d921dcf0c634c697bded5bedddf5588566626aa8f4c608298f7f5f7a13a3c", 1),
    ("2418cc6c4c8399cce671be9430fe6701ea09abf42fa8407804e9d6802c8bf2eb", 1),
    ("b517fede95007cdc108f882863b7c9e8778911be1bbc18cc010ac159266cf815", 1),
    ("646a3758046c02d1eff6b889ed6a89d13ee8dd2eb1749b33eca756a00727124e", 1),
    ("eeb5212f9492f39f2c01e48c9e3be7992402a1d688cd315ddfa8021c9667f713", 1),
    ("2708bc3f138d80bb4863b733a543912427a65ac439175055fe848674a2dfd935", 2),
    ("b8630f105667e74d5cde1c329c0385035a28c381f9e8195777d45b919305f68c", 3),
    ("86c1d185caea74184ba4585c9a1e18e7b75df81437d2c98fb70ec2e00851f56f", 2),
    ("955d212a26c8b77af7c55b1b7e375d7024855f8d1ab51ec88cd1cfd9f625e033", 2),
    # Construction / real-estate AP tooling in the same class as the entries above.
    # Both the fused and spaced spellings are listed: matching is exact per n-gram,
    # so a one-word entry never matches the two-word form, or vice versa.
    ("c024b43b13548acf45c5da8c5be04fde9a0fb2a42df69972238857f0a40ba32e", 1),
    ("5379c826c1ab2b0990f7a5808dd8a59bd20a805841ee07d815c01c87d88fd328", 2),
    ("55af965522a877fbb91c42cc317bc592e7ac2282c8b986ea24d9d19b87f3e6de", 1),
    ("cfbd7ff585b42feee8f81570af72fb00fbbcf5b6277ce8b6991a287a089320b5", 2),
)

#: Non-confidential canary phrases used ONLY by the matcher self-tests.
#: They are deliberately absent from DENYLIST so the surface sweeps never
#: match them, and their plaintext presence here is harmless by design.
CANARIES: Tuple[str, ...] = (
    "orange zebra placeholder",
    "quixotic canary",
)

SURFACES = (
    "atlas_data.py",
    "generate.py",
    "README.md",
    "artifact-html",
    "tree-sweep",
    "repo-sweep",
)

#: File types included in the tree sweeps.
TEXT_SUFFIXES = {
    ".py", ".md", ".html", ".htm", ".txt", ".json",
    ".ini", ".cfg", ".toml", ".yml", ".yaml", ".css", ".js", ".svg",
}

_SKIP_DIR_PARTS = {"__pycache__", ".pytest_cache", ".git", "node_modules"}

_NGRAM_SIZES = tuple(sorted({n for _, n in DENYLIST}))

_TOKEN_RE = re.compile(r"[0-9a-z]+(?:'[0-9a-z]+)*")


def _tokens(text: str) -> List[str]:
    """Normalize text into the token stream the digests were built from."""
    folded = (
        text.replace("’", "'").replace("‘", "'")
            .replace("“", '"').replace("”", '"')
            .lower()
    )
    return _TOKEN_RE.findall(folded)


def _normalize_term(term: str) -> str:
    return " ".join(_tokens(term))


def _digest(term: str) -> str:
    return hashlib.sha256(_normalize_term(term).encode("utf-8")).hexdigest()


def ngram_digests(text: str) -> Dict[int, Set[str]]:
    """Hash every candidate n-gram of the token stream, per n-gram size."""
    toks = _tokens(text)
    out: Dict[int, Set[str]] = {}
    for n in _NGRAM_SIZES:
        grams: Set[str] = set()
        for i in range(len(toks) - n + 1):
            gram = " ".join(toks[i:i + n])
            grams.add(hashlib.sha256(gram.encode("utf-8")).hexdigest())
        out[n] = grams
    return out


def _tree_text(root: Path) -> str:
    parts = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if _SKIP_DIR_PARTS.intersection(path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


@pytest.fixture(scope="session")
def surface_digests() -> Dict[str, Dict[int, Set[str]]]:
    surfaces = {
        "atlas_data.py": (ATLAS_DIR / "atlas_data.py").read_text(encoding="utf-8"),
        "generate.py": (ATLAS_DIR / "generate.py").read_text(encoding="utf-8"),
        "README.md": README_PATH.read_text(encoding="utf-8"),
        "artifact-html": ARTIFACT_PATH.read_text(encoding="utf-8"),
        "tree-sweep": _tree_text(ATLAS_DIR),
        "repo-sweep": _tree_text(REPO_DIR),
    }
    return {name: ngram_digests(text) for name, text in surfaces.items()}


# ---------------------------------------------------------------------------
# The matrix: every denied digest x every surface.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize(
    "digest,nwords", DENYLIST, ids=[d[:10] for d, _ in DENYLIST]
)
def test_surface_is_clean_of_denied_term(
    digest: str, nwords: int, surface: str,
    surface_digests: Dict[str, Dict[int, Set[str]]],
) -> None:
    if digest in surface_digests[surface][nwords]:
        pytest.fail(
            "denied term (digest %s..., %d-word) found on surface %r; "
            "the matched text is intentionally not printed"
            % (digest[:12], nwords, surface)
        )


# ---------------------------------------------------------------------------
# Linter self-checks: the deny list is intact and the matcher works.
# ---------------------------------------------------------------------------

def test_deny_list_has_expected_size() -> None:
    assert len(DENYLIST) == 89


def test_deny_list_digests_are_unique() -> None:
    assert len({d for d, _ in DENYLIST}) == len(DENYLIST)


def test_deny_list_entries_are_wellformed() -> None:
    for digest, nwords in DENYLIST:
        assert re.fullmatch(r"[0-9a-f]{64}", digest), digest
        assert 1 <= nwords <= max(_NGRAM_SIZES)
    # One-way property: no digest may equal the hash of the empty string.
    empty = hashlib.sha256(b"").hexdigest()
    assert all(d != empty for d, _ in DENYLIST)


def test_canaries_are_not_in_the_deny_list() -> None:
    for canary in CANARIES:
        assert (_digest(canary), len(_tokens(canary))) not in DENYLIST


def test_matcher_detects_seeded_canary_case_insensitively() -> None:
    canary = CANARIES[0]
    n = len(_tokens(canary))
    for haystack in (
        "x " + canary.upper() + " y",
        "path\\" + canary.replace(" ", "_") + ";rest",
        canary.replace(" ", "\n    "),
        canary.replace(" ", "-"),
    ):
        assert _digest(canary) in ngram_digests(haystack)[n], haystack


def test_matcher_respects_word_boundaries() -> None:
    canary = CANARIES[1]
    n = len(_tokens(canary))
    fused = "prefix" + canary.replace(" ", "") + "suffix"
    assert _digest(canary) not in ngram_digests(fused)[n]


def test_every_surface_is_present_and_nonempty(
    surface_digests: Dict[str, Dict[int, Set[str]]],
) -> None:
    for surface in SURFACES:
        assert any(surface_digests[surface][n] for n in _NGRAM_SIZES), surface
