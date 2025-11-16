from core.arguments import Argument, ActionSpec, VerifySpec, ArgFramework

def generate_scraper_AF(state, expected):
    args = {}
    attacks = set()
    attacks_info = []

    args['A_write_html'] = Argument(
        id='A_write_html', domain='desktop', topic='scraper_task',
        pre=(),
        action=ActionSpec('write_file', {'path': 'project/sample.html', 'kind': 'html'}),
        effects=('fs:sample.html exists',),
        verify=VerifySpec('file_exists', {'path': 'project/sample.html', 'timeout_s': 5.0}),
        priority=30, deadline_ms=50, source="planner"
    )

    args['A_write_scraper'] = Argument(
        id='A_write_scraper', domain='desktop', topic='scraper_task',
        pre=(),
        action=ActionSpec('write_file', {'path': 'project/scraper.py', 'kind': 'scraper'}),
        effects=('fs:scraper.py exists', 'sha:expected'),
        verify=VerifySpec('file_hash_equal', {
            'path': 'project/scraper.py',
            'expected_sha256': expected['scraper_sha'],
            'timeout_s': 5.0
        }),
        priority=25, deadline_ms=60, source="planner"
    )

    args['A_write_tests'] = Argument(
        id='A_write_tests', domain='desktop', topic='scraper_task',
        pre=(),
        action=ActionSpec('write_file', {'path': 'project/test_scraper.py', 'kind': 'tests'}),
        effects=('fs:test exists',),
        verify=VerifySpec('file_hash_equal', {
            'path': 'project/test_scraper.py',
            'expected_sha256': expected['test_sha'],
            'timeout_s': 5.0
        }),
        priority=25, deadline_ms=70, source="planner"
    )

    args['A_run_tests'] = Argument(
        id='A_run_tests', domain='desktop', topic='scraper_task',
        pre=('fs:scraper.py exists', 'fs:test exists'),
        action=ActionSpec('run_pytest', {'path': 'project'}),
        effects=('tests:pass',),
        verify=VerifySpec('proc_exitcode_ok', {
            'cmd': ['python', '-m', 'pytest', '-q'],
            'cwd': 'project',
            'timeout_s': 60.0
        }),
        priority=15, deadline_ms=90, source="planner"
    )

    args['A_run_scraper'] = Argument(
        id='A_run_scraper', domain='desktop', topic='scraper_task',
        pre=('tests:pass',),
        action=ActionSpec('run_py', {'script': 'project/scraper.py', 'args': []}),
        effects=('out:output.json exists', 'sha:out_expected'),
        verify=VerifySpec('file_hash_equal', {
            'path': 'project/output.json',
            'expected_sha256': expected['out_sha'],
            'timeout_s': 5.0
        }),
        priority=10, deadline_ms=100, source="planner"
    )

    # Precedence/guard attacks (for AF reporting; solver still uses pair set)
    for frm, to, reason in [
        ("A_run_tests",   "A_write_scraper", "Cannot run tests before scraper exists"),
        ("A_run_tests",   "A_write_html",    "Cannot run tests before sample HTML exists"),
        ("A_run_tests",   "A_write_tests",   "Cannot run tests before tests are written"),
        ("A_run_scraper", "A_run_tests",     "Run scraper only after tests pass"),
        ("A_run_scraper", "A_write_scraper", "Cannot run scraper before scraper.py exists"),
        ("A_run_scraper", "A_write_html",    "Cannot run scraper before sample HTML exists"),
    ]:
        attacks.add((frm, to))
        attacks_info.append({"from": frm, "to": to, "reason": reason, "source": "planner"})

    af = ArgFramework(args=args, attacks=attacks)
    af.attacks_info = attacks_info
    return af
