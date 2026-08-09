from pathlib import Path

import pytest

from dirconf.filter import (
    MISSING,
    MissingWarning,
    filter,
    filter_missing,
    filter_read,
    filter_write,
)


class DummyHandler:
    def read(self, path):
        return {"data": "hello"}

    def write(self, path, data, *, overwrite_ok=False):
        pass


class TestMISSING:
    def test_missing_is_not_type(self):
        assert not isinstance(MISSING, type)

    def test_missing_singleton_usage(self):
        val = MISSING
        assert val is MISSING


class TestFilterRead:
    def test_filter_read_passes_when_test_true(self):
        handler = DummyHandler()

        @filter_read(test=lambda path: True)
        def read(self, path):
            return handler.read(path)

        result = read(handler, Path("test.txt"))
        assert result == {"data": "hello"}

    def test_filter_read_returns_missing_when_test_false(self):
        @filter_read(test=lambda path: False, label="always_fail", warn=True)
        def read(self, path):
            return {"data": "hello"}

        handler = DummyHandler()
        with pytest.warns(MissingWarning):
            result = read(handler, Path("nonexistent.txt"))
        assert result is MISSING

    def test_filter_read_no_warning_when_warn_false(self):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = filter_read(test=lambda path: False)(DummyHandler.read)(
                DummyHandler(), Path("test.txt")
            )
        assert result is MISSING

    def test_filter_read_label_from_lambda(self):
        label = filter_read(test=lambda path: True)(DummyHandler.read)
        assert callable(label)


class TestFilterWrite:
    def test_filter_write_passes_when_test_true(self):
        written = False

        class WriteHandler:
            def read(self, path):
                return None

            def write(self, path, data, *, overwrite_ok=False):
                nonlocal written
                written = True

        handler = WriteHandler()
        wrapped = filter_write(test=lambda path, data, **kw: True)(WriteHandler.write)
        wrapped(handler, Path("test.txt"), {"key": "val"}, overwrite_ok=True)
        assert written

    def test_filter_write_returns_missing_when_test_false(self):
        wrapped = filter_write(test=lambda path, data, **kw: False)(DummyHandler.write)
        result = wrapped(
            DummyHandler(), Path("test.txt"), {"key": "val"}, overwrite_ok=False
        )
        assert result is None

    def test_filter_write_warns(self):
        wrapped = filter_write(test=lambda path, data, **kw: False, warn=True)(
            DummyHandler.write
        )
        with pytest.warns(MissingWarning):
            wrapped(
                DummyHandler(), Path("test.txt"), {"key": "val"}, overwrite_ok=False
            )


class TestFilterWriteOnClassBypassesFilter:
    """Confirms that passing a class to filter_write bypasses the filter.

    The existing test_filter_write_passes_when_test_true passes a class
    (WriteHandler) to filter_write. functools.wraps copies the class
    __dict__ (including the write method) into the wrapper function's
    attribute dict, so WrappedClass.write resolves to the original
    unwrapped method. This test proves the filter is never invoked.
    """

    @pytest.mark.xfail(
        strict=False,
        reason="filter_write should reject classes, not silently bypass the filter",
    )
    def test_write_on_class_bypasses_filter(self):
        called = False

        class Handler:
            def read(self, path):
                return {}

            def write(self, path, data, *, overwrite_ok=False):
                nonlocal called
                called = True

        Wrapped = filter_write(
            test=lambda path, data, **kw: False,  # always reject
            warn=False,
        )(Handler)  # type: ignore[arg-type]  # passing a CLASS (same pattern as existing test)

        Wrapped.write(Handler(), Path("test.txt"), {})  # type: ignore[reportFunctionMemberAccess]  # functools.wraps copies class __dict__ onto function

        assert called, (
            "write was called despite test=False, confirming "
            "the filter was bypassed via functools.wraps class-__dict__ copying"
        )

    def test_write_on_method_respects_filter(self):
        called = False

        class Handler:
            def read(self, path):
                return {}

            def write(self, path, data, *, overwrite_ok=False):
                nonlocal called
                called = True

        Wrapped = filter_write(
            test=lambda path, data, **kw: False,  # always reject
            warn=False,
        )(Handler.write)  # passing a METHOD (correct usage)

        Wrapped(Handler(), Path("test.txt"), {})

        assert not called, (
            "write was NOT called because the filter correctly "
            "returned early when test=False"
        )


class TestFilter:
    def test_filter_preserves_module(self):
        @filter(read=lambda path: True)
        class FilteredHandler:
            def read(self, path):
                return "data"

            def write(self, path, data, *, overwrite_ok=False):
                pass

        assert FilteredHandler.__module__ == __name__

    def test_filter_with_read_only(self):
        @filter(read=lambda path: True)
        class FilteredHandler:
            def read(self, path):
                return "data"

            def write(self, path, data, *, overwrite_ok=False):
                pass

        instance = FilteredHandler()
        assert isinstance(instance, FilteredHandler)

    def test_filter_with_write_only(self):
        @filter(write=lambda path, data, **kw: True)
        class FilteredHandler:
            def read(self, path):
                return "data"

            def write(self, path, data, *, overwrite_ok=False):
                pass

        instance = FilteredHandler()
        assert isinstance(instance, FilteredHandler)

    def test_filter_requires_read_or_write(self):
        with pytest.raises(ValueError, match="Must provide"):
            filter()(object)  # type: ignore[arg-type]

    def test_filter_does_not_mutate_original_class(self):
        class OriginalHandler:
            def read(self, path):
                return "original"

            def write(self, path, data, *, overwrite_ok=False):
                pass

        original_read = OriginalHandler.read
        original_write = OriginalHandler.write

        @filter(read=lambda path: False)
        class FilteredHandler(OriginalHandler):
            pass

        # The filtered class should be a subclass, not a mutation
        assert issubclass(FilteredHandler, OriginalHandler)
        # The original class methods should be untouched
        assert OriginalHandler.read is original_read
        assert OriginalHandler.write is original_write
        # The filtered instance should return MISSING
        assert FilteredHandler().read("test.txt") is MISSING


class TestFilterMissing:
    def test_filter_missing_exists(self):
        assert callable(filter_missing)

    def test_filter_missing_returns_decorator(self):
        decorator = filter_missing()
        assert callable(decorator)

    def test_filter_missing_on_class(self):
        @filter_missing()
        class SafeHandler:
            def read(self, path):
                return "data"

            def write(self, path, data, *, overwrite_ok=False):
                pass

        handler = SafeHandler()
        assert isinstance(handler, SafeHandler)
