from mena_agent.dedupe_rank import dedupe_and_rank


def test_tier_a_outranks_tier_c_even_with_lower_keyword_score():
    items = [
        {
            "title": "Ferry From Beirut To Batroun launches",
            "source_name": "The 961",
            "tier": "C",
            "snippet": "Lebanon Beirut travel ferry",
        },
        {
            "title": "Hezbollah says it downed Israeli drone",
            "source_name": "Reuters",
            "tier": "A",
            "snippet": "Hezbollah Israel Lebanon security",
        },
    ]
    ranked = dedupe_and_rank(items)
    assert ranked[0]["source_name"] == "Reuters"
    assert ranked[1]["source_name"] == "The 961"


def test_near_duplicate_titles_are_merged():
    items = [
        {"title": "Gaza ceasefire talks resume in Cairo", "source_name": "A", "tier": "B", "snippet": ""},
        {"title": "Gaza ceasefire talks resume in Cairo today", "source_name": "B", "tier": "A", "snippet": ""},
    ]
    ranked = dedupe_and_rank(items)
    assert len(ranked) == 1
    # The higher-tier duplicate should be the one kept as representative.
    assert ranked[0]["source_name"] == "B"


def test_empty_input_returns_empty_list():
    assert dedupe_and_rank([]) == []
