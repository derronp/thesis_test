from core.arguments import Argument, ActionSpec, VerifySpec, ArgFramework

def generate_scraper_AF(state, expected):
    args = {}
    attacks = set()

    args['A_write_html'] = Argument(
        id='A_write_html', domain='desktop', topic='scraper_task',
        pre=(), action=ActionSpec('write_file', {'path':'project/sample.html','kind':'html'}),
        effects=('fs:sample.html exists',),
        verify=VerifySpec('file_exists', {'path':'project/sample.html','timeout_s':5.0}),
        priority=30, deadline_ms=50
    )
    args['A_write_scraper'] = Argument(
        id='A_write_scraper', domain='desktop', topic='scraper_task',
        pre=(), action=ActionSpec('write_file', {'path':'project/scraper.py','kind':'scraper'}),
        effects=('fs:scraper.py exists','sha:expected'),
        verify=VerifySpec('file_hash_equal', {'path':'project/scraper.py','expected_sha256': expected['scraper_sha'], 'timeout_s':5.0}),
        priority=25, deadline_ms=60
    )
    args['A_write_tests'] = Argument(
        id='A_write_tests', domain='desktop', topic='scraper_task',
        pre=(), action=ActionSpec('write_file', {'path':'project/test_scraper.py','kind':'tests'}),
        effects=('fs:test exists',),
        verify=VerifySpec('file_hash_equal', {'path':'project/test_scraper.py','expected_sha256': expected['test_sha'], 'timeout_s':5.0}),
        priority=25, deadline_ms=70
    )
    args['A_run_tests'] = Argument(
        id='A_run_tests', domain='desktop', topic='scraper_task',
        pre=('fs:scraper.py exists','fs:test exists'), 
        action=ActionSpec('run_pytest', {'path':'project'}),
        effects=('tests:pass',),
        verify=VerifySpec('proc_exitcode_ok', {'cmd':['python','-m','pytest','-q'], 'cwd':'project', 'timeout_s': 60.0}),
        priority=15, deadline_ms=90
    )
    args['A_run_scraper'] = Argument(
        id='A_run_scraper', domain='desktop', topic='scraper_task',
        pre=('tests:pass',),
        action=ActionSpec('run_py', {'script':'project/scraper.py','args': []}),
        effects=('out:output.json exists','sha:out_expected'),
        verify=VerifySpec('file_hash_equal', {'path':'project/output.json','expected_sha256': expected['out_sha'], 'timeout_s':5.0}),
        priority=10, deadline_ms=100
    )
    attacks |= {('A_write_scraper','A_run_tests'), ('A_write_tests','A_run_tests'), ('A_write_html','A_run_tests')}
    attacks |= {('A_run_tests','A_run_scraper')}  # tests gate the run

    return ArgFramework(args=args, attacks=attacks)
