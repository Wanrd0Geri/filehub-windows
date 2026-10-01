from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from filehub.automation.models import Predicate, ConditionGroup, Action, Rule, RuleSet
from filehub.automation.conditions import FileFacts, evaluate, first_match

NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def facts(**kwargs):
    return FileFacts(Path('C:/samples/A.PNG'), None, kind='image', size_bytes=100,
                     created=NOW-timedelta(days=2), modified=NOW-timedelta(hours=1), **kwargs)


@pytest.mark.parametrize('field,operator,value,matched', [
    ('name', 'equals', 'a.png', True), ('name', 'contains', 'A.', True),
    ('name', 'glob', '*.pNg', True), ('name', 'starts_with', 'a', True),
    ('name', 'ends_with', '.PNG', True), ('extension', 'equals', 'PNG', True),
    ('extension', 'glob', '*.PNG', True), ('extension', 'contains', 'NG', True),
    ('extension', 'ends_with', 'NG', True),
    ('size_bytes', 'ge', 100, True), ('size_bytes', 'gt', 100, False),
    ('created', 'eq', '2026-09-29T05:00:00-07:00', True),
    ('modified', 'lt', '2026-10-01T11:00:00+00:00', False),
    ('kind', 'equals', 'file', True), ('kind', 'equals', 'folder', False),
])
def test_text_numbers_dates_and_kind(field, operator, value, matched):
    result = evaluate(Predicate(field, operator, value), facts(), NOW)
    assert result.matched is matched
    assert result.status in ('true', 'false')
    assert result.reason and result.actual is not None


@pytest.mark.parametrize('mode,known,status', [
    ('all', True, 'unavailable'), ('all', False, 'false'),
    ('any', True, 'true'), ('any', False, 'unavailable'),
    ('none', True, 'false'), ('none', False, 'unavailable'),
])
def test_unknown_ages_never_make_negative_group_match(mode, known, status):
    condition = ConditionGroup(mode, (Predicate('size_bytes', 'eq', 100 if known else 101),
                                     Predicate('first_seen_age_seconds', 'ge', 1)))
    result = evaluate(condition, facts(), NOW)
    assert result.status == status
    assert len(result.children) == 2
    assert '不可用' in result.children[1].reason


def test_nested_none_all_any_and_snapshot_observations():
    f = facts(first_seen=NOW-timedelta(seconds=60), stable_since=NOW-timedelta(hours=3))
    nested = ConditionGroup('all', (
        ConditionGroup('any', (Predicate('name', 'equals', 'missing'), Predicate('extension', 'equals', '.png'))),
        ConditionGroup('none', (Predicate('kind', 'equals', 'folder'),)),
        Predicate('first_seen_age_seconds', 'ge', 60), Predicate('stable_age_seconds', 'eq', 3600)))
    assert evaluate(nested, f, NOW).matched
    assert not evaluate(Predicate('stable_age_seconds', 'gt', 3600), f, NOW).matched


def test_future_observation_and_modified_timestamp_unavailable():
    f = FileFacts(Path('C:/a'), None, modified=NOW+timedelta(seconds=1),
                  first_seen=NOW+timedelta(seconds=1), stable_since=NOW-timedelta(seconds=10))
    assert evaluate(Predicate('first_seen_age_seconds', 'ge', 0), f, NOW).status == 'unavailable'
    assert evaluate(Predicate('stable_age_seconds', 'ge', 0), f, NOW).status == 'unavailable'
    with pytest.raises(ValueError): evaluate(Predicate('name', 'equals', 'a'), f, NOW.replace(tzinfo=None))


def test_first_enabled_match_marks_later_unevaluated_and_selected_disabled(tmp_path):
    a = Action('rename', {'pattern': 'done{ext}'})
    disabled = Rule(name='停用', condition=Predicate('name', 'glob', '*'), actions=(a,))
    winner = Rule(name='命中', enabled=True, condition=Predicate('extension', 'equals', 'png'), actions=(a,))
    later = Rule(name='后续', enabled=True, condition=Predicate('name', 'glob', '*'), actions=(a,))
    rules = RuleSet((disabled, winner, later))
    result = first_match(rules, facts(), NOW)
    assert result.rule == winner
    assert result.ruleset_revision == rules.revision
    assert result.evaluations[0].status == 'disabled'
    assert result.evaluations[2].status == 'not_evaluated'
    assert result.evaluations[1].explanation.matched
    assert first_match(rules, facts(), NOW, rule_id=disabled.id).rule == disabled
    scoped = Rule(condition=Predicate('name', 'glob', '*'), actions=(a,), enabled=True, scope=(str(tmp_path),))
    assert first_match(RuleSet((scoped,)), facts(), NOW).rule is None


def test_capture_directory_sum_and_extension_distinction(tmp_path):
    folder = tmp_path/'folder.png'
    folder.mkdir()
    (folder/'a').write_bytes(b'123')
    (folder/'nested').mkdir()
    (folder/'nested'/'b').write_bytes(b'45')
    captured = FileFacts.capture(folder)
    assert captured.kind == 'folder' and captured.size_bytes == 5
    assert not evaluate(Predicate('extension', 'equals', 'png'), captured, NOW).matched
    assert evaluate(Predicate('kind', 'equals', 'folder'), captured, NOW).matched
    assert not evaluate(Predicate('kind', 'equals', 'file'), captured, NOW).matched


def test_invalid_scope_cannot_add_unconfigured_watch_root(tmp_path):
    a = Action('rename', {'pattern': 'done{ext}'})
    r = Rule(enabled=True, condition=Predicate('name', 'glob', '*'), actions=(a,), scope=('C:/samples',))
    result = first_match(RuleSet((r,)), facts(), NOW, configured_watch_roots=(tmp_path,))
    assert result.rule is None and result.evaluations[0].status == 'invalid_scope'


def test_explicit_selected_disabled_rule_tests_sample_outside_watch_scope(tmp_path):
    r = Rule(condition=Predicate('name', 'glob', '*'), actions=(Action('rename', {'pattern': 'done{ext}'}),),
             scope=(str(tmp_path),))
    result = first_match(RuleSet((r,)), facts(), NOW, rule_id=r.id, configured_watch_roots=(tmp_path,))
    assert result.rule == r and result.explicit_selection
    assert not result.rule.enabled


@pytest.mark.parametrize('created,want', [(NOW-timedelta(seconds=30), 'true'), (NOW+timedelta(seconds=1), 'unavailable')])
def test_stable_age_respects_recent_and_future_creation(created, want):
    f = FileFacts(Path('C:/a'), None, created=created, modified=NOW-timedelta(hours=1),
                  stable_since=NOW-timedelta(hours=3))
    result = evaluate(Predicate('stable_age_seconds', 'eq', 30), f, NOW)
    assert result.status == want


@pytest.mark.parametrize('which', ['file_created', 'file_modified', 'directory_created', 'directory_modified'])
def test_stable_directory_age_uses_latest_captured_child_timestamp(which):
    from filehub.models import Fingerprint
    from filehub.trees import TreeFingerprint, DirectoryIdentity
    old = int((NOW-timedelta(hours=3)).timestamp()*1e9)
    recent = int((NOW-timedelta(seconds=10)).timestamp()*1e9)
    child = Fingerprint(1, 2, 3, recent if which == 'file_modified' else old, 'hash', recent if which == 'file_created' else old)
    directory = DirectoryIdentity('child', 1, 3, recent if which == 'directory_created' else old,
                                  recent if which == 'directory_modified' else old)
    fp = TreeFingerprint(1, 1, 3, old, 'tree', old, (), (('child/a', child),), (directory,))
    f = FileFacts(Path('C:/folder'), fp, kind='folder', created=NOW-timedelta(hours=3),
                  modified=NOW-timedelta(hours=3), stable_since=NOW-timedelta(hours=3))
    assert evaluate(Predicate('stable_age_seconds', 'eq', 10), f, NOW).matched


def test_automatic_unscoped_rule_only_matches_configured_top_level(tmp_path):
    r = Rule(enabled=True, condition=Predicate('name', 'glob', '*'), actions=(Action('rename', {'pattern': 'done{ext}'}),))
    rules = RuleSet((r,))
    assert first_match(rules, facts(), NOW, configured_watch_roots=(tmp_path,)).rule is None
    nested = FileFacts(tmp_path/'nested'/'a.png', None)
    assert first_match(rules, nested, NOW, watch_root=tmp_path, configured_watch_roots=(tmp_path,)).rule is None
    assert first_match(rules, nested, NOW, rule_id=r.id, configured_watch_roots=(tmp_path,)).rule == r
