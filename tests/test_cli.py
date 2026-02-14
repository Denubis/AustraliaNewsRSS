"""Tests for the australianewsrss CLI."""

from typer.testing import CliRunner

from australianewsrss.cli import app

runner = CliRunner()


class TestCLIHelp:
    """Verify CLI help output exposes expected commands and options."""

    def test_main_help_shows_discover_and_generate(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "discover" in result.output
        assert "generate" in result.output

    def test_discover_help_shows_publisher_option(self) -> None:
        result = runner.invoke(app, ["discover", "--help"])
        assert result.exit_code == 0
        assert "--publisher" in result.output

    def test_generate_help_shows_output_dir_option(self) -> None:
        result = runner.invoke(app, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--output-dir" in result.output


class TestDiscoverCommand:
    """Verify discover command placeholder behaviour."""

    def test_discover_default_all_publishers(self) -> None:
        result = runner.invoke(app, ["discover"])
        assert result.exit_code == 0
        assert "Publisher: all" in result.output

    def test_discover_specific_publisher(self) -> None:
        result = runner.invoke(app, ["discover", "--publisher", "abc"])
        assert result.exit_code == 0
        assert "Publisher: abc" in result.output


class TestGenerateCommand:
    """Verify generate command placeholder behaviour."""

    def test_generate_default_output_dir(self) -> None:
        result = runner.invoke(app, ["generate"])
        assert result.exit_code == 0
        assert "Output: _site" in result.output

    def test_generate_custom_output_dir(self) -> None:
        result = runner.invoke(app, ["generate", "--output-dir", "/tmp/out"])
        assert result.exit_code == 0
        assert "Output: /tmp/out" in result.output
