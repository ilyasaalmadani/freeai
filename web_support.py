"""Small, dependency-free parsers and routing rules for public web evidence."""
import html
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlsplit, urlunsplit


def plain(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value))).strip()


def result_url(value):
    value = html.unescape(value)
    if value.startswith("//"):
        value = "https:" + value
    try:
        parsed = urlsplit(value)
        if parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"}:
            value = parse_qs(parsed.query).get("uddg", [""])[0]
            parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        return urlunsplit(parsed._replace(fragment=""))
    except ValueError:
        return None


class SearchHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.link = None
        self.title = []
        self.snippet_tag = None
        self.snippet = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "a" and any(c in classes for c in ("result-link", "result__a")):
            self.link = attrs.get("href", "")
            self.title = []
        if self.results and any(c in classes for c in ("result-snippet", "result__snippet")):
            self.snippet_tag = tag
            self.snippet = []

    def handle_data(self, data):
        if self.link is not None:
            self.title.append(data)
        if self.snippet_tag:
            self.snippet.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.link is not None:
            url = result_url(self.link)
            title = plain(" ".join(self.title))
            if url and title:
                self.results.append({"title": title, "url": url, "summary": ""})
            self.link = None
        if tag == self.snippet_tag:
            self.results[-1]["summary"] = plain(" ".join(self.snippet))[:1000]
            self.snippet_tag = None


STOP = set("apa apakah adalah yang dan atau di ke dari dengan untuk ini itu saya kamu tolong coba cari carikan mencari searching search web internet informasi tentang info berikan jelaskan terbaru terkini hari saat sekarang resmi dokumentasi the a an is are of for in on to and or what how please find search official documentation latest current today".split())


def rank_results(results, query):
    site = re.search(r"\bsite:([\w.-]+)", query, re.I)
    terms = [word for word in dict.fromkeys(re.findall(r"[\w.+-]+", query.casefold()))
             if word not in STOP and (len(word) >= 3 or word in {"ai", "go"})]
    ranked, seen = [], set()
    for row in results:
        url = result_url(row.get("url", ""))
        if not url or url in seen:
            continue
        host = urlsplit(url).hostname
        if site and host != site[1] and not host.endswith("." + site[1]):
            continue
        text = (row.get("title", "") + " " + url + " " + row.get("summary", "")).casefold()
        score = sum(word in text for word in terms)
        minimum = 1 if len(terms) <= 3 else 2
        if terms and score < minimum:
            continue
        seen.add(url)
        ranked.append((score, {"title": plain(row.get("title", "")), "url": url,
                               "summary": plain(row.get("summary", ""))[:1000]}))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in ranked[:6]]


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.text = []
        self.title = []
        self.in_title = False
        self.anchors = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.anchors[attrs["id"]] = len(self.text)
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self.hidden.append(tag)
        if tag == "title":
            self.in_title = True
        if tag in {"p", "br", "div", "h1", "h2", "h3", "li", "pre"}:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)
        if self.in_title:
            self.title.append(data)

    def content(self, anchor=None):
        parts = self.text[self.anchors.get(anchor, 0):] if anchor else self.text
        return "\n".join(line for line in (plain(part) for part in "".join(parts).splitlines()) if line)


def needs_search(prompt):
    text = prompt.casefold()
    explicit = r"\b(web search|searching|search the web|search online|browse|googl\w*|cari(?:kan)? (?:di (?:web|internet)|informasi|info|berita|tahu)|coba cari|telusuri|riset)\b"
    temporal = r"\b(terbaru|terkini|hari ini|minggu ini|bulan ini|tahun ini|latest|up.to.date|today|current (?:version|price|release)|cuaca|berita|jadwal|harga (?:bitcoin|emas|saham|btc))\b"
    direct = re.search(r"^\s*(?:tolong\s+)?(?:cari(?:kan)?|search|find|temukan)\s+", text)
    local = re.search(r"\b(?:cari|search|find|temukan)\s+(?:file|teks|fungsi|function|kode|code|di proyek|di folder)\b", text)
    return bool(re.search(explicit, text) or re.search(temporal, text) or (direct and not local))


def uncertain_answer(text):
    return bool(re.search(r"(?:saya (?:tidak|belum) (?:tahu|yakin)|pengetahuan saya (?:terbatas|hanya|sampai)|tidak (?:bisa|dapat|memiliki akses)[^.\n]{0,65}(?:internet|web|real.time)|knowledge cutoff|I (?:do not|don't) know|I (?:cannot|can't) (?:browse|access the internet))", text, re.I))


def search_query(prompt):
    prompt = re.sub(r"```.*?```", " ", prompt, flags=re.S)
    prompt = re.sub(r"(?:/Users/|/home/|~/)\S+", " ", prompt)
    prompt = re.sub(r"\b(?:sk-|gsk_|freellmapi-)[A-Za-z0-9_-]+", "", prompt)
    prompt = re.sub(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+", "", prompt)
    return plain(prompt)[:240]
