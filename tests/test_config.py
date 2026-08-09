import json
from pathlib import Path

import pytest

from dirconf import DirConfig, Handler, make_dirconfig, register_handler
from dirconf.config import (
    ValidationError,
    ValidationResult,
    _str_is_json,
    _str_is_path,
)
from dirconf.filter import filter_missing
from dirconf.handler import handler_registry
from dirconf.node import Node


class SimpleHandler:
    def __init__(self):
        self.data = {}

    def read(self, path):
        with open(path) as f:
            return json.load(f)

    def write(self, path, data, *, overwrite_ok=False):
        with open(path, "w" if overwrite_ok else "x") as f:
            json.dump(data, f)


@pytest.fixture(autouse=True)
def clean_registry():
    original = handler_registry.copy()
    yield
    handler_registry.clear()
    handler_registry.update(original)


class TestDirConfig:
    def test_dirconfig_is_handler(self):
        assert isinstance(DirConfig(), Handler)

    def test_tree_empty(self):
        mc = DirConfig()
        result = mc.tree()
        assert result == ""

    def test_tree_with_nodes(self):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        result = config().tree(details=False)
        assert "a" in result

    def test_str(self):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        result = str(config())
        assert "TestConfig" in result

    def test_nodes(self):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {
                "a": {"path": "a.json", "handler": "simple"},
                "b": {"path": "b.json", "handler": "simple"},
            },
        )
        nodes = list(config().nodes())
        assert len(nodes) == 2
        assert all(isinstance(n, Node) for n in nodes)

    def test_read(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        (tmp_path / "a.json").write_text('{"key": "value"}')

        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        data = config().read(tmp_path)
        assert data == {"a": {"key": "value"}}

    def test_write(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        output_dir = tmp_path / "output"
        config().write(output_dir, {"a": {"key": "value"}})
        assert (output_dir / "a.json").exists()

    def test_write_creates_directory(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        output_dir = tmp_path / "new" / "nested" / "dir"
        config().write(output_dir, {"a": {"key": "value"}})
        assert (output_dir / "a.json").exists()

    def test_call(self):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": SimpleHandler}},
        )
        instance = config()
        result = instance()
        assert isinstance(result, type(instance))
        assert result.a.path == instance.a.path  # type: ignore[attr-defined]


class TestMakeDirConfig:
    def test_module_is_detected(self):
        config = make_dirconfig("TestConfig", {})

        assert config.__module__ == __name__

    def test_module_can_be_overridden(self):
        config = make_dirconfig("TestConfig", {}, module="custom.module")

        assert config.__module__ == "custom.module"

    def test_from_dict(self):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        assert issubclass(config, DirConfig)

    def test_from_json_string(self):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        spec = json.dumps({"a": {"path": "a.json", "handler": "simple"}})
        config = make_dirconfig("TestConfig", spec)
        assert issubclass(config, DirConfig)

    def test_from_json_file(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps({"a": {"path": "a.json", "handler": "simple"}}))
        config = make_dirconfig("TestConfig", spec_file)
        assert issubclass(config, DirConfig)

    def test_from_path_string(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps({"a": {"path": "a.json", "handler": "simple"}}))
        config = make_dirconfig("TestConfig", str(spec_file))
        assert issubclass(config, DirConfig)

    def test_handler_only(self):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {"a": {"handler": "simple"}},
        )
        instance = config(a="a.json")  # type: ignore[call-arg]
        assert instance.a.path == Path("a.json")  # type: ignore[attr-defined]

    def test_neither_path_nor_handler(self):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        config = make_dirconfig(
            "TestConfig",
            {"a": {}},
        )
        instance = config(a="a.json")  # type: ignore[call-arg]
        assert instance.a.path == Path("a.json")  # type: ignore[attr-defined]

    def test_path_only_raises(self):
        with pytest.raises(NotImplementedError):
            make_dirconfig("TestConfig", {"a": {"path": "a.json"}})

    def test_unsupported_spec_type(self):
        with pytest.raises(TypeError, match="Unsupported type"):
            make_dirconfig("TestConfig", 123)  # type: ignore[arg-type]


class TestStrIsJson:
    def test_valid_json(self):
        assert _str_is_json('{"key": "value"}')

    def test_invalid_json(self):
        assert not _str_is_json("not json")

    def test_json_array(self):
        assert _str_is_json("[1, 2, 3]")


class TestStrIsPath:
    def test_existing_path(self, tmp_path):
        assert _str_is_path(str(tmp_path))

    def test_nonexistent_relative_path(self):
        assert not _str_is_path("configs/my_config.json")

    def test_nonexistent_absolute_path(self):
        assert _str_is_path("/absolute/path.txt")

    def test_invalid_path_characters(self):
        assert not _str_is_path("not_a_path_xyz<<<<")

    def test_random_string(self):
        assert not _str_is_path("not a path at all!!<>?")


class TestValidationResult:
    def test_str_passed(self):
        result = ValidationResult(valid=True)
        assert str(result) == "ValidationResult: PASSED"

    def test_repr_passed(self):
        result = ValidationResult(valid=True)
        assert repr(result) == "ValidationResult: PASSED"

    def test_str_failed_with_missing(self):
        result = ValidationResult(valid=False, missing=[Path("a.json"), Path("b.json")])
        s = str(result)
        assert "FAILED" in s
        assert "Missing (2)" in s
        assert "a.json" in s
        assert "b.json" in s

    def test_str_failed_with_unreadable(self):
        result = ValidationResult(valid=False, unreadable=[Path("secret.txt")])
        s = str(result)
        assert "FAILED" in s
        assert "Unreadable (1)" in s
        assert "secret.txt" in s

    def test_str_failed_with_both(self):
        result = ValidationResult(
            valid=False,
            missing=[Path("a.json")],
            unreadable=[Path("b.json")],
        )
        s = str(result)
        assert "Missing (1)" in s
        assert "Unreadable (1)" in s


class TestValidationError:
    def test_exception_message_uses_result_str(self):
        result = ValidationResult(valid=False, missing=[Path("a.json")])
        exc = ValidationError(result)
        assert str(exc) == str(result)

    def test_exception_stores_result(self):
        result = ValidationResult(valid=False, missing=[Path("a.json")])
        exc = ValidationError(result)
        assert exc.result is result


class TestValidate:
    def test_passes_for_valid_directory(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        (tmp_path / "a.json").write_text('{"key": "value"}')

        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        result = config().validate(tmp_path)
        assert result

    def test_detects_missing_file(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        result = config().validate(tmp_path)
        assert result is not None
        assert result.valid is False
        assert len(result.missing) == 1
        assert result.missing[0].name == "a.json"

    def test_raises_in_strict_mode(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        with pytest.raises(ValidationError) as exc_info:
            config().validate(tmp_path, strict=True)
        assert exc_info.value.result.valid is False

    def test_detects_missing_base_directory(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        nonexistent = tmp_path / "nonexistent"

        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        result = config().validate(nonexistent, strict=False)
        assert result is not None
        assert result.valid is False
        assert len(result.missing) == 1

    def test_multiple_missing_files(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        config = make_dirconfig(
            "TestConfig",
            {
                "a": {"path": "a.json", "handler": "simple"},
                "b": {"path": "b.json", "handler": "simple"},
            },
        )
        result = config().validate(tmp_path)
        assert result is not None
        assert len(result.missing) == 2

    def test_unreadable_file_detected(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])
        unreadable = tmp_path / "a.json"
        unreadable.write_text('{"key": "value"}')
        unreadable.chmod(0o000)

        config = make_dirconfig(
            "TestConfig",
            {"a": {"path": "a.json", "handler": "simple"}},
        )
        try:
            result = config().validate(tmp_path)
            assert result is not None
            assert result.valid is False
            assert len(result.unreadable) == 1
        finally:
            unreadable.chmod(0o644)

    def test_nested_dirconfig_recurses(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        inner_config = make_dirconfig(
            "InnerConfig",
            {"inner_file": {"path": "inner.json", "handler": "simple"}},
        )

        outer_config = make_dirconfig(
            "OuterConfig",
            {
                "outer_file": {"path": "outer.json", "handler": "simple"},
                "subdir": {"path": "sub", "handler": inner_config},
            },
        )

        (tmp_path / "outer.json").write_text('{"outer": true}')
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "inner.json").write_text('{"inner": true}')

        result = outer_config().validate(tmp_path)
        assert result

    def test_nested_dirconfig_detects_missing_child(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        inner_config = make_dirconfig(
            "InnerConfig",
            {"inner_file": {"path": "inner.json", "handler": "simple"}},
        )

        outer_config = make_dirconfig(
            "OuterConfig",
            {
                "subdir": {"path": "sub", "handler": inner_config},
            },
        )

        (tmp_path / "sub").mkdir()

        result = outer_config().validate(tmp_path)
        assert result is not None
        assert result.valid is False
        assert any("inner.json" in str(p) for p in result.missing)

    def test_empty_dirconfig_passes(self, tmp_path):
        config = DirConfig()
        result = config.validate(tmp_path)
        assert result


class TestValidateOptionalMissing:
    def test_filter_missing_handler_produces_optional_missing(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        @filter_missing()
        class OptionalHandler:
            def read(self, path):
                return {}

            def write(self, path, data, *, overwrite_ok=False):
                pass

        config = make_dirconfig(
            "TestConfig",
            {
                "required": {"path": "required.json", "handler": "simple"},
                "optional": {"path": "optional.file", "handler": OptionalHandler},
            },
        )

        (tmp_path / "required.json").write_text('{"key": "value"}')

        result = config().validate(tmp_path)
        assert result.valid is True
        assert len(result.missing) == 0
        assert len(result.optional_missing) == 1
        assert result.optional_missing[0].name == "optional.file"

    def test_validation_passes_when_only_optional_missing(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        @filter_missing()
        class OptionalHandler:
            def read(self, path):
                return {}

            def write(self, path, data, *, overwrite_ok=False):
                pass

        config = make_dirconfig(
            "TestConfig",
            {"optional": {"path": "optional.file", "handler": OptionalHandler}},
        )

        result = config().validate(tmp_path)
        assert result.valid is True
        assert len(result.optional_missing) == 1

    def test_validation_fails_when_required_and_optional_missing(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        @filter_missing()
        class OptionalHandler:
            def read(self, path):
                return {}

            def write(self, path, data, *, overwrite_ok=False):
                pass

        config = make_dirconfig(
            "TestConfig",
            {
                "required": {"path": "required.json", "handler": "simple"},
                "optional": {"path": "optional.file", "handler": OptionalHandler},
            },
        )

        result = config().validate(tmp_path)
        assert result.valid is False
        assert len(result.missing) == 1
        assert len(result.optional_missing) == 1

    def test_repr_shows_optional_missing_on_pass(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        @filter_missing()
        class OptionalHandler:
            def read(self, path):
                return {}

            def write(self, path, data, *, overwrite_ok=False):
                pass

        config = make_dirconfig(
            "TestConfig",
            {"optional": {"path": "optional.file", "handler": OptionalHandler}},
        )

        result = config().validate(tmp_path)
        repr_str = repr(result)
        assert "PASSED" in repr_str
        assert "Optional missing (1)" in repr_str
        assert "optional.file" in repr_str

    def test_repr_shows_optional_missing_on_fail(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        @filter_missing()
        class OptionalHandler:
            def read(self, path):
                return {}

            def write(self, path, data, *, overwrite_ok=False):
                pass

        config = make_dirconfig(
            "TestConfig",
            {
                "required": {"path": "required.json", "handler": "simple"},
                "optional": {"path": "optional.file", "handler": OptionalHandler},
            },
        )

        result = config().validate(tmp_path)
        repr_str = repr(result)
        assert "FAILED" in repr_str
        assert "Missing (1)" in repr_str
        assert "Optional missing (1)" in repr_str

    def test_unreadable_directory_does_not_recurse(self, tmp_path):
        register_handler("simple", SimpleHandler, extensions=[".json"])

        inner_config = make_dirconfig(
            "InnerConfig",
            {"inner_file": {"path": "inner.json", "handler": "simple"}},
        )

        outer_config = make_dirconfig(
            "OuterConfig",
            {
                "subdir": {"path": "sub", "handler": inner_config},
            },
        )

        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "inner.json").write_text('{"inner": true}')
        (tmp_path / "sub").chmod(0o000)

        try:
            result = outer_config().validate(tmp_path)
            assert result.valid is False
            assert len(result.unreadable) == 1
            assert result.missing == []
        finally:
            (tmp_path / "sub").chmod(0o755)
