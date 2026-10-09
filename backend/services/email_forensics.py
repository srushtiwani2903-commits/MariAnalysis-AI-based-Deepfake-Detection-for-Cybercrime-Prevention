"""Email format validation and content-anomaly forensics.

Validates a pasted email against the standard header format
(From / To / Subject / Date + body) and flags even the smallest deviation,
plus anything hidden or "different" inside the text:

  * active content  - HTML tags, inline on* handlers, javascript:/data: URIs,
                      entity- or percent-encoded <script>.
  * Unicode abuse   - bidirectional controls, zero-width / invisible chars,
                      unusual spaces, stacked combining marks and
                      mixed-script (Cyrillic / Greek) homoglyphs.
  * link abuse      - display-text vs href mismatch, '@' tricks, raw IP hosts,
                      punycode (xn--), shorteners, high-risk TLDs, deep
                      subdomains.
  * header abuse    - Reply-To / Return-Path domain differing from From.

Every function returns JSON-serialisable data. ``analyze_email_forensics`` is
the single entry point used by services.analyze_email.
"""
import re
import unicodedata
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# Header format
# --------------------------------------------------------------------------- #
_HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9\-]{1,40}):[ \t]*(.*)$")
_STD_HEADERS = ("from", "to", "subject", "date")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")

# --------------------------------------------------------------------------- #
# Active content / script detection
# --------------------------------------------------------------------------- #
_ACTIVE_TAGS = (
    (re.compile(r"<\s*script", re.I), "<script>"),
    (re.compile(r"<\s*iframe", re.I), "<iframe>"),
    (re.compile(r"<\s*object", re.I), "<object>"),
    (re.compile(r"<\s*embed", re.I), "<embed>"),
    (re.compile(r"<\s*form", re.I), "<form>"),
    (re.compile(r"<\s*svg", re.I), "<svg>"),
    (re.compile(r"<\s*base", re.I), "<base>"),
)
_PASSIVE_TAGS = (
    (re.compile(r"<\s*img", re.I), "<img>"),
    (re.compile(r"<\s*meta", re.I), "<meta>"),
    (re.compile(r"<\s*link", re.I), "<link>"),
    (re.compile(r"<\s*style", re.I), "<style>"),
    (re.compile(r"<\s*audio", re.I), "<audio>"),
    (re.compile(r"<\s*video", re.I), "<video>"),
    (re.compile(r"<\s*table", re.I), "<table>"),
    (re.compile(r"<\s*html", re.I), "<html>"),
    (re.compile(r"<\s*body", re.I), "<body>"),
)
_EVENT_RE = re.compile(
    r"\bon(?:error|load|click|mouse\w+|focus|blur|submit|input|change|animationstart)\s*=",
    re.I)
_JS_URI_RE = re.compile(r"\b(?:javascript|vbscript|data:text/html)\s*:", re.I)
_ENCODED_MARKUP_RE = re.compile(r"(?:&lt;|&#x?0*3c;|%3c)\s*script", re.I)

# --------------------------------------------------------------------------- #
# Unicode abuse
# --------------------------------------------------------------------------- #
_BIDI = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f")
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\u2060\ufeff\u180e\u115f\u1160\u00ad")
_ODD_SPACES = frozenset(
    "\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u202f\u205f\u3000")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

_SCRIPT_RANGES = {
    "Latin": ((0x0041, 0x024F), (0x1E00, 0x1EFF)),
    "Cyrillic": ((0x0400, 0x04FF), (0x0500, 0x052F), (0x2DE0, 0x2DFF)),
    "Greek": ((0x0370, 0x03FF), (0x1F00, 0x1FFF)),
    "Arabic": ((0x0600, 0x06FF), (0x0750, 0x077F)),
    "Hebrew": ((0x0590, 0x05FF),),
    "Han": ((0x4E00, 0x9FFF), (0x3400, 0x4DBF)),
    "Hiragana": ((0x3040, 0x309F),),
    "Katakana": ((0x30A0, 0x30FF),),
    "Hangul": ((0xAC00, 0xD7AF), (0x1100, 0x11FF)),
    "Devanagari": ((0x0900, 0x097F),),
}

# --------------------------------------------------------------------------- #
# Link abuse
# --------------------------------------------------------------------------- #
_LINK_RE = re.compile(r"https?://[^\s\"'<>()\[\]]+", re.I)
_ANCHOR_RE = re.compile(
    r"<a\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_HOSTLIKE_RE = re.compile(r"(?:[A-Za-z0-9\-]+\.)+[A-Za-z]{2,}", re.I)
_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "cutt.ly", "rb.gy", "shorturl.at", "tiny.cc", "rebrand.ly", "s.id",
    "lnkd.in", "adf.ly", "bit.do", "t.ly", "shorte.st", "bl.ink",
}
_BAD_TLDS = (
    ".tk", ".ml", ".ga", ".cf", ".gq", ".top", ".xyz", ".buzz", ".click",
    ".review", ".country", ".work", ".gdn", ".loan", ".kim", ".rest",
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _parse_headers(text):
    """Split the leading RFC-822-style header block from the body."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headers = []
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == "":
            body_start = i + 1
            break
        m = _HEADER_RE.match(line)
        if not m:
            body_start = i
            break
        headers.append((m.group(1).lower(), m.group(2).strip()))
        body_start = i + 1
    else:
        body_start = len(lines)
    return headers, "\n".join(lines[body_start:])


def _script_of(ch):
    cp = ord(ch)
    for name, ranges in _SCRIPT_RANGES.items():
        for lo, hi in ranges:
            if lo <= cp <= hi:
                return name
    return None


def _domain_of_email(value):
    if not value:
        return ""
    m = _EMAIL_RE.search(value)
    return m.group(1).lower() if m else ""


def _host_of(value):
    """Hostname of a URL or bare domain string, or ''."""
    v = (value or "").strip()
    if not v:
        return ""
    if "://" in v:
        try:
            v = urlparse(v).hostname or ""
        except Exception:  # noqa: BLE001
            return ""
    v = v.split("/")[0].split("?")[0].split("@")[-1]
    match = _HOSTLIKE_RE.search(v)
    return match.group(0).lower() if match else ""


def _reg(host):
    """Crude registrable domain: last two dot-labels."""
    parts = (host or "").lower().strip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else (host or "")


# --------------------------------------------------------------------------- #
# Scanners
# --------------------------------------------------------------------------- #
def _scan_scripts(text):
    active, passive = [], []
    for rx, label in _ACTIVE_TAGS:
        if rx.search(text):
            active.append(label)
    for rx, label in _PASSIVE_TAGS:
        if rx.search(text):
            passive.append(label)
    if _EVENT_RE.search(text):
        active.append("inline on* event handler")
    if _JS_URI_RE.search(text):
        active.append("javascript:/data: URI")
    if _ENCODED_MARKUP_RE.search(text):
        active.append("encoded <script> tag")
    return {"active": sorted(set(active)), "passive": sorted(set(passive))}


def _scan_unicode(text):
    bidi = zero = spaces = combining = mixed = 0
    for ch in text:
        if ch in _BIDI:
            bidi += 1
        elif ch in _ZERO_WIDTH:
            zero += 1
        elif ch in _ODD_SPACES:
            spaces += 1
        if unicodedata.combining(ch):
            combining += 1

    for word in _WORD_RE.findall(text):
        scripts = {s for s in (_script_of(c) for c in word) if s}
        if "Latin" in scripts and ({"Cyrillic", "Greek"} & scripts):
            mixed += 1

    # Non-ASCII domains (possible IDN homoglyph spoofing).
    domains = _EMAIL_RE.findall(text)
    domains += [h for h in (_host_of(u) for u in _LINK_RE.findall(text)) if h]
    if any(any(ord(c) > 127 for c in d) for d in domains):
        mixed += 1

    count = bidi + zero + spaces + mixed
    return {"bidi": bidi, "zero_width": zero, "spaces": spaces,
            "combining": combining, "mixed": mixed, "count": count}


def _scan_links(text):
    hits = []
    for url in _LINK_RE.findall(text):
        try:
            parsed = urlparse(url)
        except Exception:  # noqa: BLE001
            continue
        host = (parsed.hostname or "").lower()
        netloc = (parsed.netloc or "").lower()
        if "@" in netloc:
            hits.append("URL with '@' (credential/redirect trick)")
        if host and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            hits.append("raw IP-address link")
        if host.startswith("xn--") or ".xn--" in host:
            hits.append("punycode (xn--) link")
        if host in _SHORTENERS:
            hits.append("URL shortener")
        if any(host.endswith(t) for t in _BAD_TLDS):
            hits.append("high-risk TLD")
        if host.count(".") >= 4:
            hits.append("excessive subdomains")

    for m in _ANCHOR_RE.finditer(text):
        href, display = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        href_host = _host_of(href)
        display_host = _host_of(display)
        if href_host and display_host and _reg(href_host) != _reg(display_host):
            hits.append("link text/href domain mismatch")

    return {"count": len(hits), "hits": sorted(set(hits))}


def _scan_header_mismatch(hdict):
    from_dom = _domain_of_email(hdict.get("from", ""))
    reply_dom = _domain_of_email(hdict.get("reply-to", ""))
    return_dom = _domain_of_email(hdict.get("return-path", ""))
    issues = []
    if from_dom and reply_dom and _reg(from_dom) != _reg(reply_dom):
        issues.append(f"Reply-To ({reply_dom}) differs from From ({from_dom})")
    if from_dom and return_dom and _reg(from_dom) != _reg(return_dom):
        issues.append(f"Return-Path ({return_dom}) differs from From ({from_dom})")
    return issues


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def analyze_email_forensics(text):
    text = text or ""
    headers, body = _parse_headers(text)
    hdict = {}
    for key, value in headers:
        hdict.setdefault(key, value)

    checks = []
    findings = []
    flags = {"format": False, "script": False, "active_script": False,
             "unicode": False, "link": False, "header_mismatch": False}
    score = 0.0

    # ---- format conformance -------------------------------------------- #
    present = [h for h in _STD_HEADERS if h in hdict]
    missing = [h for h in _STD_HEADERS if h not in hdict]
    format_ok = len(present) >= 3
    if not format_ok:
        flags["format"] = True
        score += 0.5 * (len(missing) / len(_STD_HEADERS))
        findings.append("Email is not in the standard From/To/Subject/Date format.")
    checks.append({
        "check": "Standard email format (From/To/Subject/Date)",
        "passed": format_ok,
        "detail": ("Headers found: " + (", ".join(h.capitalize() for h in present) or "none")
                   + ("." if not missing else
                      f". Missing: {', '.join(h.capitalize() for h in missing)}.")),
        "severity": "medium" if not format_ok else "info",
    })

    # ---- active content ------------------------------------------------- #
    scripts = _scan_scripts(text)
    active_hits, passive_hits = scripts["active"], scripts["passive"]
    all_hits = active_hits + passive_hits
    if active_hits:
        flags["script"] = flags["active_script"] = True
        score += min(1.0, 0.6 + 0.15 * len(active_hits))
        findings.append("Active HTML/script content: " + ", ".join(active_hits) + ".")
    elif passive_hits:
        flags["script"] = True
        score += min(0.4, 0.12 * len(passive_hits))
        findings.append("Embedded HTML markup (no active script): "
                        + ", ".join(passive_hits) + ".")
    if all_hits:
        detail = ("Active: " + ", ".join(active_hits) + ". ") if active_hits else ""
        if passive_hits:
            detail += "Embedded markup: " + ", ".join(passive_hits) + "."
    else:
        detail = "No tags, event handlers or script URIs."
    checks.append({
        "check": "No active HTML / script content",
        "passed": not all_hits,
        "detail": detail,
        "severity": "high" if active_hits else ("medium" if passive_hits else "info"),
    })

    # ---- Unicode abuse -------------------------------------------------- #
    uni = _scan_unicode(text)
    if uni["count"]:
        flags["unicode"] = True
        score += min(1.0, 0.5 + 0.1 * uni["count"])
    uni_parts = []
    if uni["bidi"]:
        uni_parts.append(f"{uni['bidi']} bidirectional control(s)")
    if uni["zero_width"]:
        uni_parts.append(f"{uni['zero_width']} zero-width/invisible char(s)")
    if uni["mixed"]:
        uni_parts.append(f"{uni['mixed']} mixed-script/homoglyph word(s)/domain(s)")
    if uni["spaces"]:
        uni_parts.append(f"{uni['spaces']} unusual space(s)")
    if uni["combining"]:
        uni_parts.append(f"{uni['combining']} combining mark(s)")
    if uni_parts:
        findings.append("Hidden/obfuscated Unicode: " + ", ".join(uni_parts) + ".")
    checks.append({
        "check": "No hidden or mixed-script Unicode",
        "passed": not uni["count"],
        "detail": ("Detected " + ", ".join(uni_parts) + ".")
                  if uni_parts else "Plain single-script text with no hidden characters.",
        "severity": "high" if (uni["bidi"] or uni["zero_width"] or uni["mixed"]) else
                    ("medium" if uni["count"] else "info"),
    })

    # ---- link abuse ----------------------------------------------------- #
    link = _scan_links(text)
    if link["count"]:
        flags["link"] = True
        score += min(1.0, 0.25 * link["count"])
        findings.append("Suspicious link(s): " + ", ".join(link["hits"]) + ".")
    checks.append({
        "check": "No deceptive or risky links",
        "passed": link["count"] == 0,
        "detail": ("Found " + ", ".join(link["hits"]) + ".")
                  if link["count"] else "No risky URL patterns detected.",
        "severity": "high" if link["count"] >= 2 else ("medium" if link["count"] else "info"),
    })

    # ---- header mismatch ------------------------------------------------ #
    hm = _scan_header_mismatch(hdict)
    if hm:
        flags["header_mismatch"] = True
        score += 0.5
        findings.append("Header mismatch: " + "; ".join(hm) + ".")
    checks.append({
        "check": "Sender headers are consistent",
        "passed": not hm,
        "detail": ("; ".join(hm) + ".") if hm
                  else "From / Reply-To / Return-Path domains agree.",
        "severity": "medium" if hm else "info",
    })

    return {
        "score": round(min(1.0, score), 3),
        "format_ok": format_ok,
        "header_count": len(headers),
        "headers": hdict,
        "present_headers": present,
        "missing_headers": missing,
        "body_length": len(body),
        "flags": flags,
        "checks": checks,
        "findings": findings,
    }
