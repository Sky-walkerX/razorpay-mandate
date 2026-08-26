from mandate.gateway.resolve import CategoryResolver, Resolver

CURATED = {"toor dal": "grocery", "basmati rice": "grocery", "craft lager": "alcohol",
           "red wine": "alcohol", "cigarettes": "tobacco", "potato chips": "snacks"}

def test_exact_title_resolves():
    assert CategoryResolver(CURATED).resolve("s1", "Toor Dal 1kg") == "grocery"

def test_alcohol_resolves():
    assert CategoryResolver(CURATED).resolve("s2", "Craft Lager can") == "alcohol"

def test_unknown_title_returns_none():
    assert CategoryResolver(CURATED).resolve("s3", "Celebration Kit") is None

def test_unknown_titles_are_queued_for_offline_classification():
    r = CategoryResolver(CURATED)
    r.resolve("s3", "Party Essentials Pack")
    assert ("s3", "Party Essentials Pack") in r.pending_classification()

def test_learned_category_is_used_next_time():
    r = CategoryResolver(CURATED)
    assert r.resolve("s3", "Celebration Kit") is None
    r.learn("s3", "alcohol")
    assert r.resolve("s3", "Celebration Kit") == "alcohol"

def test_cache_persists_across_instances(tmp_path):
    p = tmp_path / "cats.json"
    a = CategoryResolver(CURATED, cache_path=p)
    a.resolve("s9", "Mystery Box"); a.learn("s9", "grocery")
    assert CategoryResolver(CURATED, cache_path=p).resolve("s9", "Mystery Box") == "grocery"

def test_resolver_facade_exposes_both():
    r = Resolver(merchants={"zepto": "Zepto"}, categories=CURATED)
    assert r.merchant("Zepto") == "zepto" and r.category("s1", "Toor Dal") == "grocery"
