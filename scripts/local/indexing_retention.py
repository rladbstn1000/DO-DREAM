#!/usr/bin/env python3
"""Read-only inventory for retention review. There is intentionally no deletion mode."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid


def classify(executions, collections, referenced_names, object_names):
    """Classifications are observations, never proof that an object is safe to delete."""
    physical = {row['name']: row['id'] for row in collections}
    if len(physical) != len(collections):
        raise ValueError('Duplicate physical collection name')
    ledger_names = set()
    retained = []
    for row in executions:
        name = row['candidate']
        if name in ledger_names:
            raise ValueError('Duplicate ledger candidate')
        ledger_names.add(name)
        if row['isActivePointer']:
            category = 'active' if row['executionState'] == 'ACTIVE' else 'active_inconsistent'
        elif row['executionState'] == 'ACTIVE' and row['contentDigest'] and (row['actualChunks'] or 0) > 0:
            category = 'previous-verified'
        elif row['executionState'] in ('FAILED', 'EXPIRED', 'SUPERSEDED', 'REVOKED'):
            category = 'failed-unreferenced'
        else:
            category = 'retained_in_progress_or_unverified'
        retained.append({**row, 'classification': category, 'physicalExists': name in physical,
                         'collectionId': physical.get(name), 'action': 'retain'})
    for row in collections:
        if row['name'] not in ledger_names:
            retained.append({'candidate': row['name'], 'collectionId': row['id'],
                             'classification': 'retained_unknown_collection',
                             'physicalExists': True, 'action': 'retain'})
    referenced = set(referenced_names)
    present = set(object_names)
    if any(not re.fullmatch(r'[0-9a-f]{64}\.(json|pdf)', name) for name in present | referenced):
        raise ValueError('Unexpected hashed object filename')
    objects = [{'filename': name, 'classification': 'referenced_current' if name in referenced else 'retained_unreferenced',
                'action': 'retain', 'safeToDelete': False} for name in sorted(present)]
    return {
        'collections': retained,
        'candidateCleanupReviewOnly': [row['candidate'] for row in retained
            if row['classification'] == 'failed-unreferenced' and row['physicalExists']],
        'objects': objects,
        'currentReferenceFilenamesAbsentFromDirectory': sorted(referenced - present),
        'activePointerProblems': [row['candidate'] for row in retained if row.get('isActivePointer') and
            (row['classification'] != 'active' or not row['physicalExists'])],
        'counts': {'ledgerExecutions': len(executions), 'physicalCollections': len(collections),
                   'objectFilenames': len(present), 'currentReferenceFilenames': len(referenced)},
    }


def collect():
    from manage import compose_args, clean_env

    def execute(service, args, stdin=None):
        result = subprocess.run(compose_args('exec', '-T', service, *args), input=stdin,
                                capture_output=True, text=True, env=clean_env(), timeout=90)
        if result.returncode:
            raise RuntimeError('Read-only inventory command failed for ' + service)
        return result.stdout.strip()

    def sql(statement):
        # SQL is fixed source text; generated credentials stay in the mysql process environment.
        return execute('mysql', ['sh', '-c', 'MYSQL_PWD="$MYSQL_PASSWORD" mysql --default-character-set=utf8mb4 -N -B -u"$MYSQL_USER" "$MYSQL_DATABASE"'], statement)

    available = set(sql("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='uploaded_files';").splitlines())
    columns = [name for name in ('s3key', 'jsons3key', 'question_jsons3key', 'concept_check_jsons3key') if name in available]
    if not {'s3key', 'jsons3key'} <= set(columns):
        raise RuntimeError('Expected current object reference columns unavailable')
    refs = ' UNION ALL '.join('SELECT ' + name + ' AS object_key FROM uploaded_files WHERE ' + name + ' IS NOT NULL' for name in columns)
    statement = """START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;
SELECT JSON_OBJECT('record','execution','executionId',e.id,'jobId',j.job_id,
 'resourceKind',r.resource_kind,'resourceId',r.resource_id,'sourceRevision',j.source_revision,
 'indexSpec',j.index_spec,'generation',e.generation,'candidate',e.candidate_name,
 'jobState',j.state,'executionState',e.state,'isActivePointer',IF(r.active_execution_id=e.id,1,0),
 'actualChunks',e.actual_chunks,'contentDigest',e.content_digest)
FROM index_executions e JOIN index_jobs j ON j.id=e.job_pk JOIN index_resources r ON r.id=j.resource_pk
ORDER BY e.id;
SELECT DISTINCT JSON_OBJECT('record','reference','filename',CONCAT(SHA2(object_key,256),IF(RIGHT(object_key,4)='.pdf','.pdf','.json')))
FROM (""" + refs + """) object_references WHERE object_key<>'';
COMMIT;
"""
    rows = [json.loads(line) for line in sql(statement).splitlines() if line]
    executions = [{key: value for key, value in row.items() if key != 'record'} for row in rows if row['record'] == 'execution']
    for row in executions:
        row['isActivePointer'] = bool(row['isActivePointer'])
    referenced = [row['filename'] for row in rows if row['record'] == 'reference']
    # Only Chroma collection identifiers and local hashed filenames leave the AI process.
    # No collection documents/vectors, object contents, source keys or signed URLs are read.
    code = '''import json,os,re
from pathlib import Path
from app.indexing.chroma import client
from app.config import LOCAL_OBJECT_STORAGE_DIR
base=Path('/app/be-local-data/objects')
if Path(LOCAL_OBJECT_STORAGE_DIR)!=base or base.is_symlink() or not base.is_dir():
 raise RuntimeError('Expected read-only object directory unavailable')
names=[];unclassified=0
for entry in os.scandir(base):
 if re.fullmatch(r'[0-9a-f]{64}\\.(json|pdf)',entry.name) and entry.is_file(follow_symlinks=False):names.append(entry.name)
 else:unclassified+=1
c=client();collections=[]
for offset in range(0,10000,100):
 batch=c.list_collections(limit=100,offset=offset)
 if not batch:break
 for name in batch:
  row=c.get_collection(name=str(name),embedding_function=None)
  collections.append({'name':str(name),'id':str(row.id)})
else:raise RuntimeError('Inventory exceeds reviewed bound')
print(json.dumps({'collections':collections,'objectNames':sorted(names),'unclassifiedDirectoryEntriesRetained':unclassified}))
'''
    physical = json.loads(execute('ai', ['python', '-c', code]))
    report = classify(executions, physical['collections'], referenced, physical['objectNames'])
    report['unclassifiedDirectoryEntriesRetained'] = physical['unclassifiedDirectoryEntriesRetained']
    report['referenceColumns'] = columns
    return report


def self_test():
    import unittest

    class RetentionTests(unittest.TestCase):
        def row(self, state='ACTIVE', pointer=False):
            return {'candidate': 'idx_test_g1', 'executionState': state, 'isActivePointer': pointer,
                    'contentDigest': 'd' * 64, 'actualChunks': 2}
        def report(self, row, collections=None):
            return classify([row], collections if collections is not None else [{'name': 'idx_test_g1', 'id': 'synthetic'}], [], [])
        def test_active_is_never_cleanup_candidate(self):
            report = self.report(self.row(pointer=True))
            self.assertEqual(report['collections'][0]['classification'], 'active')
            self.assertEqual(report['candidateCleanupReviewOnly'], [])
        def test_previous_verified_retained(self):
            self.assertEqual(self.report(self.row())['collections'][0]['classification'], 'previous-verified')
        def test_failed_is_review_only_and_retained(self):
            report = self.report(self.row('FAILED'))
            self.assertEqual(report['candidateCleanupReviewOnly'], ['idx_test_g1'])
            self.assertEqual(report['collections'][0]['action'], 'retain')
        def test_building_is_not_cleanup_candidate(self):
            self.assertEqual(self.report(self.row('BUILDING'))['candidateCleanupReviewOnly'], [])
        def test_missing_active_is_reported(self):
            self.assertEqual(self.report(self.row(pointer=True), [])['activePointerProblems'], ['idx_test_g1'])
        def test_unknown_collection_retained(self):
            report = classify([], [{'name': 'unknown', 'id': 'synthetic'}], [], [])
            self.assertEqual(report['collections'][0]['classification'], 'retained_unknown_collection')
        def test_unreferenced_file_is_not_safe_to_delete(self):
            name = 'a' * 64 + '.json'; report = classify([], [], [], [name])
            self.assertEqual(report['objects'][0]['classification'], 'retained_unreferenced')
            self.assertFalse(report['objects'][0]['safeToDelete'])
        def test_current_reference_and_absence_are_distinct(self):
            present = 'a' * 64 + '.pdf'; absent = 'b' * 64 + '.json'
            report = classify([], [], [present, absent], [present])
            self.assertEqual(report['objects'][0]['classification'], 'referenced_current')
            self.assertEqual(report['currentReferenceFilenamesAbsentFromDirectory'], [absent])
        def test_arbitrary_paths_rejected(self):
            with self.assertRaises(ValueError): classify([], [], [], ['../private.json'])
        def test_duplicate_collection_identity_rejected(self):
            with self.assertRaises(ValueError): self.report(self.row(), [{'name':'same','id':'1'},{'name':'same','id':'2'}])

    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(RetentionTests))
    return 0 if result.wasSuccessful() else 1


def main():
    if sys.argv[1:] == ['--self-test']:
        return self_test()
    if sys.argv[1:]:
        raise SystemExit('Only --self-test or read-only inventory with no arguments is supported')
    from manage import ROOT, source_identity
    started = datetime.now(timezone.utc)
    report = {'mode': 'READ_ONLY_DRY_RUN', 'deleteSupported': False, 'action': 'retain_all',
              'safeToDelete': False, 'startedAt': started.isoformat(), 'source': source_identity(),
              'limitations': ['MySQL and Chroma inventories are separate observations, not one transaction.',
                'Hashed filenames do not recover source keys or all historical object references.',
                'Missing physical files may be legacy virtual fixtures; absence is not deletion evidence.',
                'No collection content, object content or source keys are included.']}
    try:
        report.update(collect())
        report['status'] = 'FAIL' if report['activePointerProblems'] else 'PASS'
        code = 1 if report['activePointerProblems'] else 0
    except Exception as error:
        report.update(status='FAIL', errorType=type(error).__name__)
        code = 1
    report.update(completedAt=datetime.now(timezone.utc).isoformat(), exitCode=code)
    output = ROOT / '.local/phase3b/results'
    output.mkdir(parents=True, exist_ok=True)
    name = 'index-retention-dry-run-' + started.strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8] + '.json'
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    with (output / name).open('x') as stream: stream.write(text)
    (output / 'index-retention-dry-run-latest.json').write_text(text)
    print(json.dumps({'status': report['status'], 'exitCode': code, 'evidence': str(output / name),
                      'counts': report.get('counts'), 'action': 'retain_all'}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
