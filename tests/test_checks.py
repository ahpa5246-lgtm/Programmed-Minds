import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from programmed_minds.checks import run_checks, _execute


class ChecksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.target = self.root / 'project'
        self.target.mkdir()
        (self.target / 'app.py').write_text('print("hello")\n')
        self.output = self.root / 'report'

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, name='gitleaks', **options):
        return run_checks(self.target, {'checks': [{'name': name, **options}]}, self.output)

    def test_required_missing_blocks(self):
        with patch('programmed_minds.checks.shutil.which', return_value=None):
            report = self.run_check()
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['checks'][0]['status'], 'missing')
        self.assertTrue((self.output / 'checks.json').exists())

    def test_disabled_required_and_empty_checks_block(self):
        report = self.run_check(enabled=False, reason='No installation')
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['checks'][0]['status'], 'not_applicable')
        empty = run_checks(self.target, {'checks': []}, self.root / 'empty')
        self.assertEqual(empty['status'], 'blocked')

    def test_fixed_argv_nonzero_and_optional_failure(self):
        with patch('programmed_minds.checks.shutil.which', return_value='/usr/bin/gitleaks'), patch('programmed_minds.checks._execute', return_value=(1, .01, 'findings', False)) as execute:
            report = self.run_check(required=False)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['checks'][0]['status'], 'failed')
        self.assertEqual(execute.call_args.args[0], ['gitleaks', 'dir', '--redact', '--no-banner', str(self.target)])

    def test_requirement_mapping_is_copied_from_user_config(self):
        with patch('programmed_minds.checks.shutil.which', return_value='/bin/gitleaks'), patch('programmed_minds.checks._execute', return_value=(0, .1, 'clean', False)):
            report = self.run_check(requirement_ids=['REQ-1'])
        self.assertEqual(report['checks'][0]['requirement_ids'], ['REQ-1'])

    def test_success_and_hash(self):
        with patch('programmed_minds.checks.shutil.which', return_value='/bin/gitleaks'), patch('programmed_minds.checks._execute', return_value=(0, .1, 'no findings', False)):
            report = self.run_check()
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(len(report['sha256']), 64)
        self.assertEqual(json.loads((self.output / 'checks.json').read_text()), report)
        import hashlib
        log = self.output / report['checks'][0]['log']
        self.assertEqual(report['checks'][0]['log_sha256'], hashlib.sha256(log.read_bytes()).hexdigest())

    def test_unknown_command_or_extra_argv_rejected(self):
        for check in [{'name': 'echo; touch /tmp/pwn'}, {'name': 'gitleaks', 'argv': ['sh', '-c', 'echo bad']}]:
            with self.assertRaises(ValueError):
                run_checks(self.target, {'checks': [check]}, self.output)

    def test_strict_types_duplicates_and_unknown_keys(self):
        for config in [{'checks': [{'name': 'gitleaks', 'required': 'false'}]}, {'checks': [{'name': 'gitleaks'}, {'name': 'gitleaks'}]}, {'checks': [], 'owned_urls': 'https://example.com'}]:
            with self.assertRaises(ValueError):
                run_checks(self.target, config, self.output)

    def test_output_ancestor_symlink_and_existing_directory_rejected(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        (self.root / 'alias').symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(ValueError):
            run_checks(self.target, {'checks': []}, self.root / 'alias' / 'new')
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            self.run_check(enabled=False)

    def test_target_symlink_escape_and_host_root_rejected(self):
        (self.target / 'outside').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_check()
        with self.assertRaises(ValueError):
            run_checks(Path('/'), {'checks': []}, self.output)

    def test_network_requires_exact_owned_url_and_optin(self):
        for url in ['https://example.com', 'https://user:pass@example.com', 'http://localhost:8000/\n', 'http://localhost:8000/?token=secret', 'http://localhost:8000/%0a']:
            with patch('programmed_minds.checks._execute') as execute:
                report = run_checks(self.target, {'checks': [{'name': 'zap', 'url': url}], 'owned_urls': ['http://localhost:8000/'], 'allow_network': True}, self.root / ('url' + str(len(list(self.root.iterdir())))))
            self.assertEqual(report['status'], 'blocked')
            execute.assert_not_called()

    def test_owned_localhost_zap_is_baseline_and_warnings_fail(self):
        with patch('programmed_minds.checks.shutil.which', return_value='/bin/zap-baseline.py'), patch('programmed_minds.checks._execute', return_value=(2, .1, 'WARN', False)) as execute:
            report = run_checks(self.target, {'checks': [{'name': 'zap', 'url': 'http://localhost:8000/'}], 'owned_urls': ['http://localhost:8000/'], 'allow_network': True}, self.output)
        self.assertEqual(report['checks'][0]['status'], 'failed')
        self.assertEqual(execute.call_args.args[0][:3], ['zap-baseline.py', '-t', 'http://localhost:8000/'])

    def test_no_python_tests_and_no_pgtap_files_block(self):
        for name in ['python-tests', 'pgtap']:
            report = run_checks(self.target, {'checks': [{'name': name}]}, self.root / name)
            self.assertEqual(report['status'], 'blocked')
            self.assertNotEqual(report['checks'][0]['status'], 'passed')

    def test_zero_unittest_is_not_success(self):
        (self.target / 'tests').mkdir()
        (self.target / 'tests' / 'test_empty.py').write_text('pass\n')
        report = self.run_check('python-tests')
        self.assertEqual(report['status'], 'blocked')
        self.assertNotEqual(report['checks'][0]['status'], 'passed')

    def test_zero_tests_with_zero_exit_blocks(self):
        (self.target / 'tests').mkdir()
        (self.target / 'tests' / 'test_empty.py').write_text('pass\n')
        with patch('programmed_minds.checks._execute', return_value=(0, .01, 'Ran 0 tests in 0.0s\nOK', False)):
            report = self.run_check('python-tests')
        self.assertEqual(report['status'], 'blocked')
        self.assertIn('No executed tests', report['checks'][0]['reason'])

    def test_actual_python_tests_run_and_secrets_redacted(self):
        (self.target / 'tests').mkdir()
        (self.target / 'tests' / 'test_app.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_a(self):\n  print("api_key=fixture-private-value")\n  self.assertTrue(True)\n')
        report = self.run_check('python-tests')
        self.assertEqual(report['status'], 'passed')
        self.assertNotIn('fixture-private-value', (self.output / report['checks'][0]['log']).read_text())

    def test_all_skipped_unittest_cannot_pass(self):
        (self.target / 'tests').mkdir()
        (self.target / 'tests' / 'test_app.py').write_text('import unittest\nclass T(unittest.TestCase):\n @unittest.skip("unfinished")\n def test_a(self):\n  self.fail()\n')
        report = self.run_check('python-tests')
        self.assertEqual(report['status'], 'blocked')

    def test_timeout_result_is_error(self):
        with patch('programmed_minds.checks.shutil.which', return_value='/bin/gitleaks'), patch('programmed_minds.checks._execute', return_value=(-9, .1, 'partial', True)):
            report = self.run_check()
        self.assertEqual(report['checks'][0]['status'], 'error')
        self.assertEqual(report['status'], 'blocked')

    def test_relative_config_cannot_escape(self):
        with patch('programmed_minds.checks._execute') as execute:
            report = self.run_check('semgrep', config='../outside.yaml')
        self.assertEqual(report['status'], 'blocked')
        execute.assert_not_called()

    def test_real_unittest_records_executed_test_identifier(self):
        (self.target / 'tests').mkdir()
        (self.target / 'tests' / 'test_app.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_contract(self):\n  self.assertEqual(2 + 2, 4)\n')
        report = self.run_check('python-tests')
        self.assertEqual(report['checks'][0]['test_results'], [{'id': 'test_app.T.test_contract', 'status': 'passed'}])

    def test_playwright_json_test_identifiers_exclude_flaky_and_skipped(self):
        (self.target / 'playwright.config.ts').write_text('export default {};\n')
        data = {'suites': [{'title': 'ui.spec.ts', 'specs': [
            {'title': 'good', 'tests': [{'expectedStatus': 'passed', 'status': 'expected', 'results': [{'status': 'passed'}]}]},
            {'title': 'skipped', 'tests': [{'expectedStatus': 'skipped', 'status': 'skipped', 'results': [{'status': 'skipped'}]}]},
            {'title': 'flaky', 'tests': [{'expectedStatus': 'passed', 'status': 'flaky', 'results': [{'status': 'failed'}, {'status': 'passed'}]}]},
        ]}]}
        with patch('programmed_minds.checks.shutil.which', return_value='/bin/playwright'), patch('programmed_minds.checks._execute', return_value=(0, .01, json.dumps(data), False)) as execute:
            report = run_checks(self.target, {'allow_network': True, 'owned_urls': ['http://localhost:8000/'], 'checks': [{'name': 'playwright', 'url': 'http://localhost:8000/'}]}, self.output)
        self.assertIn('--reporter=json', execute.call_args.args[0])
        self.assertEqual(report['checks'][0]['test_results'], [{'id': 'ui.spec.ts::good', 'status': 'passed'}, {'id': 'ui.spec.ts::skipped', 'status': 'skipped'}, {'id': 'ui.spec.ts::flaky', 'status': 'failed'}])

    def test_playwright_empty_or_invalid_json_blocks(self):
        (self.target / 'playwright.config.ts').write_text('export default {};\n')
        for i, log in enumerate(['{}', 'not JSON', '{"suites": []}']):
            with patch('programmed_minds.checks.shutil.which', return_value='/bin/playwright'), patch('programmed_minds.checks._execute', return_value=(0, .01, log, False)):
                report = run_checks(self.target, {'allow_network': True, 'owned_urls': ['http://localhost:8000/'], 'checks': [{'name': 'playwright', 'url': 'http://localhost:8000/'}]}, self.root / ('pw' + str(i)))
            self.assertEqual(report['status'], 'blocked')

    def test_pgtap_verbose_labels_and_skip_status(self):
        (self.target / 'tests' / 'sql').mkdir(parents=True)
        (self.target / 'tests' / 'sql' / 'schema.sql').write_text('SELECT plan(2);\n')
        with patch('programmed_minds.checks.shutil.which', return_value='/bin/pg_prove'), patch('programmed_minds.checks._execute', return_value=(0, .01, 'ok 1 - projects table exists\nok 2 - pending check # SKIP unfinished\nFiles=1, Tests=2\nResult: PASS', False)) as execute:
            report = self.run_check('pgtap', database='app_test')
        self.assertIn('--verbose', execute.call_args.args[0])
        self.assertEqual(report['checks'][0]['test_results'], [{'id': 'projects table exists', 'status': 'passed'}, {'id': 'pending check', 'status': 'skipped'}])

    def test_actual_timeout_and_log_bound(self):
        rc, duration, log, timeout = _execute([sys.executable, '-c', 'import time;print("x"*200000,flush=True);time.sleep(5)'], self.target, .1, {})
        self.assertTrue(timeout)
        self.assertLess(duration, 2)
        self.assertLess(len(log), 70000)

    def test_subprocess_has_no_shell_and_no_stdin(self):
        with patch('programmed_minds.checks.subprocess.Popen', side_effect=OSError('launch error')) as launch:
            with self.assertRaises(OSError):
                _execute(['gitleaks', 'dir', str(self.target)], self.target, 1, {})
        self.assertIs(launch.call_args.kwargs['shell'], False)
        self.assertIsNotNone(launch.call_args.kwargs['stdin'])


if __name__ == '__main__':
    unittest.main()
