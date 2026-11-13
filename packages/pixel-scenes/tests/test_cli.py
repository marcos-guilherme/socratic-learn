import json

from pixel_scenes.cli import entry_point


def test_validate_command_reports_success(tmp_path, concept_data, capsys):
    scene = tmp_path / "scene.json"
    scene.write_text(json.dumps(concept_data), encoding="utf-8")

    assert entry_point(["validate", str(scene)]) == 0
    assert "Scene is valid." in capsys.readouterr().out


def test_render_command_creates_output(
    tmp_path, concept_data, capsys
):
    scene = tmp_path / "scene.json"
    output = tmp_path / "card.png"
    scene.write_text(json.dumps(concept_data), encoding="utf-8")

    assert entry_point(["render", str(scene), "--output", str(output)]) == 0
    assert output.exists()
    assert str(output) in capsys.readouterr().out


def test_expected_error_has_no_traceback(capsys):
    assert entry_point(["validate", "missing.json"]) == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


def test_themes_lists_builtin_theme(capsys):
    assert entry_point(["themes"]) == 0
    assert capsys.readouterr().out.strip() == "cozy-classroom"


def test_example_command_protects_existing_output(tmp_path, capsys):
    output = tmp_path / "scene.json"
    output.write_text("keep", encoding="utf-8")

    assert (
        entry_point(["example", "concept-card", "--output", str(output)]) == 2
    )
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "already exists" in captured.err
    assert output.read_text(encoding="utf-8") == "keep"


def test_example_command_overwrites_with_flag(tmp_path, capsys):
    output = tmp_path / "scene.json"
    output.write_text("keep", encoding="utf-8")

    assert entry_point(
        [
            "example",
            "concept-card",
            "--output",
            str(output),
            "--overwrite",
        ]
    ) == 0
    body = json.loads(output.read_text(encoding="utf-8"))
    assert body["template"] == "concept-card"
    assert str(output) in capsys.readouterr().out
