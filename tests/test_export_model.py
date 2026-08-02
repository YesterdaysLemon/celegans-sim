"""A parameter named for export must exist, or the export must fail.

Issue #31: two of the exporter's parameter lists sat behind `if hasattr(obj, k)`, so a name
that resolved to nothing produced no header entry, no warning and no failure.
`sen_nose_touch_gain` was lost that way and stayed lost. The same shape one layer up is the
`GENES` list, where a dropped name means the runtime keeps its compiled-in literal and
every mutation on that gene silently does nothing.

So these tests are about the *failure*, not the success: each one names a way the exporter
could go quiet, and every one of them has been watched to fail against a deliberately
broken `tools/export_model.py`. Where a test could pass because a list was empty or a
lookup returned nothing, the emptiness is asserted away and that assertion has been watched
to fail too.
"""

import pytest

from tools import export_model
from tools.export_model import (
    OPTIONAL_SCALARS,
    SCALAR_GROUPS,
    Blob,
    _export_scalars,
)
from worm.params import Params


class _FakeParams:
    """Stands in for a params dataclass. Named, because the error message quotes the type."""

    def __init__(self, **fields):
        for k, v in fields.items():
            setattr(self, k, v)


def test_a_name_that_does_not_resolve_is_an_error_not_an_omission():
    b = Blob()

    with pytest.raises(KeyError) as excinfo:
        _export_scalars(b, _FakeParams(gain=2.0), ("gain", "nose_touch_gain"), "sen_")

    message = str(excinfo.value)
    assert "nose_touch_gain" in message      # the name, so it can be found
    assert "sen_nose_touch_gain" in message  # and what it would have been exported as
    assert "_FakeParams" in message          # and where it was looked for
    # Nothing is half-written: the group is rejected before any of it reaches the header.
    assert b.meta["scalars"] == {}


def test_every_missing_name_is_reported_at_once():
    # One exception per rebuild finds a batch rename one name at a time, which is how the
    # last one survived. Both names have to be in the message.
    with pytest.raises(KeyError) as excinfo:
        _export_scalars(Blob(), _FakeParams(gain=2.0),
                        ("gain", "nose_touch_gain", "vulva_gain"), "sen_")

    message = str(excinfo.value)
    assert "nose_touch_gain" in message
    assert "vulva_gain" in message


def test_present_names_all_reach_the_header_under_the_prefix():
    b = Blob()

    _export_scalars(b, _FakeParams(gain=2.0, bias=-0.5), ("gain", "bias"), "sen_")

    # Exact, not a superset: a prefix applied to some names and not others would pass a
    # containment check while emitting a constant the runtime cannot find.
    assert b.meta["scalars"] == {"sen_gain": 2.0, "sen_bias": -0.5}


def test_an_empty_group_is_refused():
    # An empty group reports no missing names and exports nothing: a check that passes
    # because it looked at nothing, which is the defect this module exists to remove.
    with pytest.raises(ValueError, match="empty group"):
        _export_scalars(Blob(), _FakeParams(gain=2.0), (), "sen_")


def test_an_optional_name_is_announced_rather_than_dropped(capsys):
    b = Blob()

    _export_scalars(b, _FakeParams(gain=2.0), ("gain", "later_gain"), "sen_",
                    optional={"sen_later_gain"})

    # Skipped, but the omission lands in the build log rather than nowhere -- the one
    # difference between an explicit optional and the `hasattr` guard that lost #31.
    assert b.meta["scalars"] == {"sen_gain": 2.0}
    assert "sen_later_gain" in capsys.readouterr().out


def test_optional_excuses_only_the_name_it_lists():
    # Otherwise a single legitimate optional entry would re-open the guard for the whole
    # group, which is the original bug wearing a different name.
    with pytest.raises(KeyError, match="typo_gain"):
        _export_scalars(Blob(), _FakeParams(gain=2.0),
                        ("gain", "later_gain", "typo_gain"), "sen_",
                        optional={"sen_later_gain"})


def test_every_declared_parameter_exists_on_its_dataclass():
    p = Params()
    checked = []
    missing = []
    for attr, prefix, names in SCALAR_GROUPS:
        obj = getattr(p, attr)
        for name in names:
            checked.append(prefix + name)
            if not hasattr(obj, name):
                missing.append("%s.%s (exported as %s)" % (attr, name, prefix + name))

    assert missing == []
    # Vacuity guards. Without these the test passes just as happily against an empty
    # registry, or one whose groups are all empty tuples -- nothing checked, green.
    assert len(SCALAR_GROUPS) >= 5
    assert all(names for _, _, names in SCALAR_GROUPS)
    assert len(checked) > 50          # measured: 83 names across 7 groups at this commit
    assert len(set(checked)) == len(checked)   # no prefix collision between groups


def test_export_emits_every_declared_parameter(tmp_path, monkeypatch):
    # The registry says what *should* be exported; this is the only check that it is
    # actually wired into `export()`, with the right dataclass under the right prefix. A
    # group could otherwise be declared, resolve cleanly, and never be called.
    monkeypatch.setattr(export_model, "_emit_ts", lambda meta, path: None)

    _, _, meta = export_model.export(str(tmp_path / "worm.model"))

    expected = [prefix + name for _, prefix, names in SCALAR_GROUPS for name in names]
    assert len(expected) > 50
    assert [k for k in expected if k not in meta["scalars"]] == []
    # And every optional name, if any is ever declared, has to belong to a group -- a stale
    # entry there would silently excuse a name nothing exports.
    assert set(OPTIONAL_SCALARS) <= set(expected)


def test_export_fails_on_a_group_naming_a_parameter_that_does_not_exist(tmp_path,
                                                                        monkeypatch):
    # The historical defect, end to end: `nose_touch_gain` on the sensory list, absent from
    # `SensoryParams`. Before the fix this exported 119 scalars and wrote the file.
    monkeypatch.setattr(export_model, "_emit_ts", lambda meta, path: None)
    monkeypatch.setattr(export_model, "SENSORY_SCALARS",
                        export_model.SENSORY_SCALARS + ("nose_touch_gain",))
    out = tmp_path / "worm.model"

    with pytest.raises(KeyError, match="nose_touch_gain"):
        export_model.export(str(out))

    # It fails before writing, so a broken list cannot leave a half-model on disk for the
    # next check to read as if it were current.
    assert not out.exists()
