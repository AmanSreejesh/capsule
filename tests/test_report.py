from capsule_cli.report import compare, render


def snapshot(node=None, **env):
    return {
        "node": {"version": node, "source": ".nvmrc"} if node else None,
        "env": env,
    }


def test_compare_requirement_changes_but_not_moved_source_files():
    before = snapshot(
        "18",
        OLD={"used_in": ["old.js"]},
        SHARED={"note": "get from admin", "used_in": ["a.js"]},
        MOVED={"used_in": ["a.js"]},
    )
    after = snapshot(
        "20",
        NEW={"used_in": ["new.js"]},
        SHARED={"note": "get from dashboard", "used_in": ["a.js"]},
        MOVED={"used_in": ["b.js"]},
    )
    result = compare(before, after)
    assert result.added == ("NEW",)
    assert result.removed == ("OLD",)
    assert result.changed == ("SHARED",)
    assert result.node_before == "18"
    assert result.node_after == "20"


def test_markdown_report_is_pr_ready():
    changes = compare(snapshot(), snapshot("20", API_KEY={"used_in": ["app.js"]}))
    text = render(changes, markdown=True, base="main")
    assert "## Capsule environment report" in text
    assert "`not declared` → `20`" in text
    assert "- `API_KEY`" in text


def test_empty_text_report():
    changes = compare(snapshot("20"), snapshot("20"))
    assert render(changes, markdown=False, base="HEAD") == (
        "No setup requirements changed compared with HEAD."
    )
