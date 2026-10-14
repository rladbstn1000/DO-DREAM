"""Pure filesystem tests; never creates services or imports their launchers."""
import hashlib
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import isolated_images as images


class ImageContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        self.tracked = []
        self.trial = self.repo / '.local/isolated/evidence-portability-20261014'

    def put(self, path, value='reviewed synthetic source\n'):
        filename = self.repo / path
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_text(value)
        self.tracked.append(path)
        return filename

    def prepare(self, component='ai'):
        base = images.COMPONENT_ROOTS[component]
        for relative in sorted(images.EXACT[component]):
            self.put(base + '/' + relative)
        if component in ('be', 'web'):
            self.put(base + '/src/example.' + ('java' if component == 'be' else 'ts'))
        elif component in ('ai', 'python-service'):
            self.put(base + '/app/main.py')
            self.put(base + '/tests/test_main.py')

    def test_be_revision_context_is_exclusive_and_preserves_original_inputs(self):
        self.prepare('be')
        original=images.materialize_context(self.repo,self.trial,'be',self.tracked)
        source=self.repo/'be/src/example.java'
        source.write_text('minimal reviewed observation change\n')
        revised=images.materialize_context(self.repo,self.trial,'be',self.tracked,revision='001-observation-01')
        images.validate_materialized_context(original)
        images.validate_materialized_context(revised)
        self.assertNotEqual(original['sourceDigest'],revised['sourceDigest'])
        self.assertIn('/revisions/001-observation-01/contexts/be',revised['contextPath'])
        with self.assertRaises(images.ContextPolicyError):
            images.materialize_context(self.repo,self.trial,'be',self.tracked,revision='001-observation-01')

    def test_revision_context_rejects_other_components_or_unbounded_paths(self):
        self.prepare('be')
        for value in ('../old','001-other-01','observation-01','001-fixed-1'):
            with self.subTest(value=value),self.assertRaises(images.ContextPolicyError):
                images.materialize_context(self.repo,self.trial,'be',self.tracked,revision=value)
        self.prepare('ai')
        with self.assertRaises(images.ContextPolicyError):
            images.materialize_context(self.repo,self.trial,'ai',self.tracked,revision='001-fixed-01')

    def test_all_component_allowlists_and_source_hash(self):
        for component in images.COMPONENT_ROOTS:
            self.prepare(component)
            selected = images.select_context(self.repo, component, self.tracked)
            self.assertIn('Dockerfile.local', selected)
            self.assertEqual(selected['Dockerfile.local'], hashlib.sha256(b'reviewed synthetic source\n').hexdigest())

    def test_no_untracked_user_or_env_reads(self):
        self.prepare()
        forbidden = ['ai/.env', 'ai/app/.env.local', 'ai/app/.DS_Store', 'ai/app/credentials.json',
                     'ai/app/.local/private.py', 'ai/app/.git/private.py', 'ai/app/private.key']
        for path in forbidden:
            self.put(path, 'MUST NOT READ')
        self.put('ai/private-user-note.txt', 'MUST NOT READ')
        self.put('ai/app/user-untracked.py', 'MUST NOT READ')
        self.tracked.remove('ai/app/user-untracked.py')
        original = images.read_source
        def checked(repo, source):
            self.assertNotIn(source, forbidden + ['ai/private-user-note.txt', 'ai/app/user-untracked.py'])
            return original(repo, source)
        with patch.object(images, 'read_source', side_effect=checked):
            selected = images.select_context(self.repo, 'ai', self.tracked)
        self.assertEqual(set(selected), images.EXACT['ai'] | {'app/main.py', 'tests/test_main.py'})

    def test_unknown_component_and_missing_inputs_rejected(self):
        with self.assertRaises(images.ContextPolicyError):
            images.select_context(self.repo, 'unknown', [])
        with self.assertRaises(images.ContextPolicyError):
            images.select_context(self.repo, 'ai', [])

    def test_malformed_and_duplicate_tracked_paths_rejected(self):
        self.prepare()
        for extra in ['../ai/app/main.py', '/ai/app/main.py', 'ai/app/../private.py', 'ai/app/main.py', 'ai/app\\private.py']:
            with self.subTest(extra=extra), self.assertRaises(images.ContextPolicyError):
                images.select_context(self.repo, 'ai', self.tracked + [extra])

    def test_source_and_ancestor_symlinks_rejected(self):
        self.prepare()
        source = self.repo / 'ai/app/main.py'
        source.unlink()
        source.symlink_to(self.repo / 'ai/Dockerfile.local')
        with self.assertRaises(images.ContextPolicyError):
            images.select_context(self.repo, 'ai', self.tracked)
        alias = self.repo / 'alias'
        alias.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises(images.ContextPolicyError):
            images.select_context(alias, 'ai', self.tracked)

    def test_hardlinked_source_rejected(self):
        self.prepare()
        os.link(self.repo / 'ai/app/main.py', self.repo / 'copy')
        with self.assertRaises(images.ContextPolicyError):
            images.select_context(self.repo, 'ai', self.tracked)

    def test_digest_is_order_independent_and_content_sensitive(self):
        a, b = '0' * 64, '1' * 64
        self.assertEqual(images.source_digest({'a.py': a, 'b.py': b}), images.source_digest({'b.py': b, 'a.py': a}))
        self.assertNotEqual(images.source_digest({'a.py': a}), images.source_digest({'a.py': b}))
        for mapping in [{}, {'../x': a}, {'.env': a}, {'x': 'not a digest'}]:
            with self.assertRaises(images.ContextPolicyError):
                images.source_digest(mapping)

    def test_materializes_exclusively_with_verifiable_record(self):
        self.prepare()
        with patch('subprocess.run', side_effect=AssertionError('execution forbidden')), \
                patch('subprocess.check_output', side_effect=AssertionError('execution forbidden')):
            result = images.materialize_context(self.repo, self.trial, 'ai', self.tracked)
        self.assertFalse(result['buildExecuted'])
        self.assertIsNone(result['imageId'])
        for row in result['sourceFiles']:
            target = Path(result['contextPath']) / row['path']
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), row['sha256'])
        with self.assertRaises(images.ContextPolicyError):
            images.materialize_context(self.repo, self.trial, 'ai', self.tracked)

    def test_unknown_or_symlink_trial_root_rejected(self):
        self.prepare()
        for target in [self.repo / '.local', self.repo / 'wrong/evidence-portability-20261014']:
            with self.assertRaises(images.ContextPolicyError):
                images.materialize_context(self.repo, target, 'ai', self.tracked)
        self.trial.parent.mkdir(parents=True)
        self.trial.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaises(images.ContextPolicyError):
            images.materialize_context(self.repo, self.trial, 'ai', self.tracked)

    def test_secret_candidate_blocks_creation_without_leaking_value(self):
        self.prepare()
        value = 'sk-' + 'Q' * 40
        (self.repo / 'ai/app/main.py').write_text('value = "' + value + '"\n')
        scan = images.scan_context(self.repo, 'ai', self.tracked)
        self.assertEqual(scan['candidates'], [{'path': 'app/main.py', 'line': 1, 'category': 'provider_token'}])
        self.assertNotIn(value, json.dumps(scan))
        with self.assertRaises(images.ContextPolicyError):
            images.materialize_context(self.repo, self.trial, 'ai', self.tracked)
        self.assertFalse(self.trial.exists())

    def test_only_narrow_known_mock_token_exception(self):
        self.prepare()
        line = 'self.key_path.write_text("OPENAI_API_KEY=sk-not-real-fixture-value-12345678\\n")\n'
        self.put('ai/tests/test_live_provider.py', line)
        scan = images.scan_context(self.repo, 'ai', self.tracked)
        self.assertEqual(scan['candidates'], [])
        self.assertEqual(len(scan['allowedFindings']), 1)
        self.put('ai/app/other.py', line)
        self.assertEqual(len(images.scan_context(self.repo, 'ai', self.tracked)['candidates']), 1)

    def test_pem_parser_exception_does_not_allow_pem_material(self):
        self.prepare('be')
        relative = 'be/src/main/java/A704/DODREAM/file/service/CloudFrontService.java'
        self.put(relative, '.replace("-----BEGIN PRIVATE KEY-----", "")\n')
        self.assertEqual(len(images.scan_context(self.repo, 'be', self.tracked)['allowedFindings']), 1)
        (self.repo / relative).write_text('-----BEGIN PRIVATE KEY-----\nPRIVATE BODY\n')
        self.assertEqual(len(images.scan_context(self.repo, 'be', self.tracked)['candidates']), 1)

    def test_materialized_context_and_repo_match_then_detect_drift(self):
        self.prepare()
        record = images.materialize_context(self.repo, self.trial, 'ai', self.tracked)
        self.assertEqual(images.validate_materialized_context(record)['status'], 'PASS')
        self.assertEqual(images.validate_repo_source(self.repo, record)['status'], 'PASS')
        target = Path(record['contextPath']) / 'app/main.py'
        target.write_text('changed copy')
        with self.assertRaises(images.ContextPolicyError):
            images.validate_materialized_context(record)
        self.assertEqual(images.validate_repo_source(self.repo, record)['status'], 'PASS')
        (self.repo / 'ai/app/main.py').write_text('changed repository')
        with self.assertRaises(images.ContextPolicyError):
            images.validate_repo_source(self.repo, record)

    def test_unexpected_materialized_paths_fail_before_any_content_read(self):
        self.prepare()
        record = images.materialize_context(self.repo, self.trial, 'ai', self.tracked)
        unknown = Path(record['contextPath']) / '.DS_Store'
        unknown.write_bytes(b'must not read')
        with patch.object(images, 'read_source', side_effect=AssertionError('must reject before reads')):
            with self.assertRaises(images.ContextPolicyError):
                images.validate_materialized_context(record)

    def test_materialized_link_and_missing_file_rejected(self):
        self.prepare()
        record = images.materialize_context(self.repo, self.trial, 'ai', self.tracked)
        target = Path(record['contextPath']) / 'app/main.py'
        target.unlink()
        with self.assertRaises(images.ContextPolicyError):
            images.validate_materialized_context(record)
        target.symlink_to(self.repo / 'ai/app/main.py')
        with self.assertRaises(images.ContextPolicyError):
            images.validate_materialized_context(record)

    def test_record_tampering_rejected_before_source_read(self):
        self.prepare()
        record = images.materialize_context(self.repo, self.trial, 'ai', self.tracked)
        for key, value in [('source', 'ai/.env'), ('path', '../env'), ('sha256', '0' * 64)]:
            tampered = copy.deepcopy(record)
            tampered['sourceFiles'][0][key] = value
            with patch.object(images, 'read_source', side_effect=AssertionError('must reject before reads')):
                with self.assertRaises(images.ContextPolicyError):
                    images.validate_repo_source(self.repo, tampered)

    def image_config(self, component):
        fixed = ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'HF_HUB_OFFLINE=1', 'TRANSFORMERS_OFFLINE=1']
        if component == 'ai': fixed.append('LANGCHAIN_TRACING_V2=false')
        if component == 'be':
            return {'Cmd': None, 'Entrypoint': ['java', '-jar', '/app/app.jar'], 'Env': ['PATH=/usr/bin'], 'Volumes': None}
        module = 'app.main:app' if component == 'ai' else 'main:app'
        return {'Cmd': ['uvicorn', module, '--host', '0.0.0.0', '--port', '8000', '--no-access-log'],
                'Entrypoint': None, 'Env': ['PATH=/usr/bin', *fixed], 'Volumes': None}

    def test_known_image_commands_and_offline_defaults(self):
        for component in ('be', 'ai', 'python-service'):
            with self.subTest(component=component):
                self.assertEqual(images.validate_image_config(component, self.image_config(component))['status'], 'PASS')
                config = self.image_config(component)
                config['Entrypoint'] = ['sh', '-c', 'unexpected command']
                with self.assertRaises(images.ContextPolicyError):
                    images.validate_image_config(component, config)
        config = self.image_config('ai')
        config['Env'].remove('HF_HUB_OFFLINE=1')
        with self.assertRaises(images.ContextPolicyError):
            images.validate_image_config('ai', config)

    def test_image_ambient_credentials_unknown_env_and_hooks_rejected(self):
        for key in ('OPENAI_API_KEY', 'AWS_ACCESS_KEY_ID', 'MYSQL_PASSWORD', 'JWT_SECRET_BASE64', 'UNKNOWN_SETTING'):
            config = self.image_config('ai')
            config['Env'].append(key + '=synthetic-not-real')
            with self.subTest(key=key), self.assertRaises(images.ContextPolicyError):
                images.validate_image_config('ai', config)
        for field, value in [('OnBuild', ['RUN unreviewed-hook']), ('Volumes', {'/unreviewed': {}})]:
            config = self.image_config('ai')
            config[field] = value
            with self.assertRaises(images.ContextPolicyError):
                images.validate_image_config('ai', config)

    def test_inherited_base_requires_independent_expected_metadata(self):
        config = {'Cmd': ['nginx', '-g', 'daemon off;'], 'Entrypoint': ['/docker-entrypoint.sh'],
                  'Env': ['PATH=/usr/bin', 'NGINX_VERSION=1.28.0'], 'Volumes': None}
        with self.assertRaises(images.ContextPolicyError):
            images.validate_image_config('web', config)
        self.assertEqual(images.validate_image_config('web', config, expected_base_config=copy.deepcopy(config))['status'], 'PASS')
        changed = copy.deepcopy(config)
        changed['Env'].append('EXTRA=value')
        with self.assertRaises(images.ContextPolicyError):
            images.validate_image_config('web', changed, expected_base_config=config)
        for component, command in [('chroma', ['chroma', 'run']), ('mysql', ['mysqld']), ('redis', ['redis-server'])]:
            base = {'Cmd': command, 'Env': ['PATH=/usr/bin']}
            self.assertEqual(images.validate_image_config(component, base, expected_base_config=copy.deepcopy(base))['status'], 'PASS')

    def test_image_metadata_duplicate_keys_and_non_literal_arguments_rejected(self):
        config = self.image_config('be')
        config['Env'].append('PATH=/other')
        with self.assertRaises(images.ContextPolicyError):
            images.validate_image_config('be', config)
        config = self.image_config('be')
        config['Entrypoint'] = 'java -jar /app/app.jar'
        with self.assertRaises(images.ContextPolicyError):
            images.validate_image_config('be', config)


if __name__ == '__main__':
    unittest.main()
