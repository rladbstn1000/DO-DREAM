"""Check metadata assertions without importing local env, contacting DB or changing fixtures."""
import ast
import copy
from pathlib import Path
import re
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'verify_fresh_indexing_schema.py'
tree=ast.parse(SOURCE.read_text())
namespace={'re':re}
# Load pure definitions only; runtime imports deliberately require the guarded local environment.
exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node,(ast.Assign,ast.FunctionDef))],type_ignores=[]),str(SOURCE),'exec'),namespace)


def valid_metadata():
    rows={}
    for table,names in namespace['REQUIRED_NONNULL'].items():
        for name in names.split():rows[table,name]=['bigint','NO','-']
    for table,name in [('grading_attempts','attempt_id'),('grading_attempts','idempotency_key'),('grading_attempts','request_fingerprint'),('index_jobs','job_id'),('index_jobs','source_hash'),('index_jobs','index_spec'),('index_executions','candidate_name'),('index_executions','claim_token')]:rows[table,name]=['varchar(64)','NO','ascii_bin']
    for table,name in [('grading_attempt_items','question_content'),('grading_attempt_items','correct_answer'),('grading_attempt_items','student_answer'),('quizzes','correct_answer'),('student_quiz_logs','student_answer')]:rows[table,name]=['text','NO','utf8mb4_0900_ai_ci']
    for name in ('attempt_id','submitted_at','snapshot_correct_answer','snapshot_question_content','snapshot_quiz_version','grading_version'):rows['student_quiz_logs',name]=['text','YES','-']
    rows['index_jobs','snapshot_json']=['longtext','NO','utf8mb4_bin']
    return {'columns':'\n'.join('\t'.join([*key,*value]) for key,value in rows.items()),
        'unique':'\n'.join('\t'.join([table,'synthetic',columns]) for table,columns in namespace['REQUIRED_UNIQUE']),
        'foreign':'\n'.join('\t'.join(row) for row in namespace['REQUIRED_FOREIGN']),
        'checks':'\n'.join('\t'.join(['index_jobs',name,'YES',clause]) for name,clause in namespace['REQUIRED_CHECK'].items())}


class FreshSchemaContractTests(unittest.TestCase):
    def test_expected_contract_and_mysql_check_quoting(self):
        self.assertEqual(namespace['contract_failures'](valid_metadata()),[])
        self.assertEqual(namespace['normalize_check']("(`resource_kind` in (_ascii'MATERIAL',_ascii'PDF'))"),
                         namespace['normalize_check']("resource_kind IN ('MATERIAL','PDF')"))
        self.assertEqual(namespace['normalize_check'](r"(`resource_kind` in (_utf8mb4\'MATERIAL\',_utf8mb4\'PDF\'))"),
                         namespace['normalize_check']("resource_kind IN ('MATERIAL','PDF')"))
        self.assertEqual(namespace['normalize_check']('OCTET_LENGTH(snapshot_json)'),namespace['normalize_check']('length(`snapshot_json`)'))
        self.assertNotEqual(namespace['normalize_check']('OCTET_LENGTH(snapshot_json)'),namespace['normalize_check']('CHAR_LENGTH(snapshot_json)'))
    def test_missing_unique_foreign_unenforced_check_and_nullable_field_fail(self):
        good=valid_metadata()
        for field in ('unique','foreign','checks'):
            broken=copy.deepcopy(good);broken[field]=''
            self.assertTrue(namespace['contract_failures'](broken),field)
        broken=copy.deepcopy(good);broken['checks']=broken['checks'].replace('\tYES\t','\tNO\t')
        self.assertTrue(any(value.startswith('invalid_check:') for value in namespace['contract_failures'](broken)))
        broken=copy.deepcopy(good);broken['columns']=broken['columns'].replace('grading_attempts\tstudent_id\tbigint\tNO','grading_attempts\tstudent_id\tbigint\tYES')
        self.assertIn('missing_nonnull:grading_attempts.student_id',namespace['contract_failures'](broken))
        broken=copy.deepcopy(good);broken['checks']=broken['checks'].replace('OCTET_LENGTH','CHAR_LENGTH')
        self.assertIn('invalid_check:ck_index_job_snapshot',namespace['contract_failures'](broken))
    def test_existing_application_schema_cannot_be_inspected_or_replayed(self):
        namespace['FRESH']='dodream_local'
        for function in ('inspect_contract','hardening_contract'):
            with self.assertRaisesRegex(RuntimeError,'restricted'):namespace[function]()

if __name__=='__main__':unittest.main()
