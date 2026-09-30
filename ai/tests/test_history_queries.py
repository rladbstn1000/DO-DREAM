"""Fixed synthetic history; real JWT/SQL policy, counted SELECTs, no provider."""
import json
import sys
import unittest
sys.path.insert(0, 'tests')
import runtime_fixture
import test_object_authorization as authz
from sqlalchemy import event
from app.common.db_session import SessionLocal, engine as authority_engine
from app.common.models import MaterialShare
from app.rag.database import SessionLocal as RagSession, engine as history_engine
from app.rag.models import ChatSession, ChatMessage, ChatMessageSources, ChatSessionIndex
from app.rag.provenance import runtime_mode


class HistoryQueryTests(unittest.TestCase):
    headers = authz.ObjectAuthorizationTests.headers

    @classmethod
    def setUpClass(cls):
        authz.ObjectAuthorizationTests.setUpClass()
        cls.client = authz.ObjectAuthorizationTests.client

    def setUp(self):
        authz.ObjectAuthorizationTests.setUp(self)

    def test_twenty_messages_keep_provenance_and_current_permissions_with_constant_queries(self):
        identity = 'hardening-synthetic-history'
        with RagSession.begin() as db:
            db.add(ChatSession(id=identity, user_id=authz.STUDENT, document_id=str(authz.DOC)))
            db.add(ChatSessionIndex(session_id=identity, source_revision=1, source_hash='a' * 64))
            for index in range(20):
                message = ChatMessage(session_id=identity, role='user' if index % 2 == 0 else 'ai', content=f'Synthetic message {index}')
                db.add(message)
                db.flush()
                if index % 2:
                    db.add(ChatMessageSources(message_id=message.id, sources_json='[]', mode_json=runtime_mode().model_dump_json()))
        counts = {'history_selects': 0, 'authority_selects': 0}

        def counted(label):
            def collect(_connection, _cursor, statement, _parameters, _context, _executemany):
                if statement.lstrip().upper().startswith('SELECT'):
                    counts[label] += 1
            return collect

        history_count, authority_count = counted('history_selects'), counted('authority_selects')
        event.listen(history_engine, 'before_cursor_execute', history_count)
        event.listen(authority_engine, 'before_cursor_execute', authority_count)
        url = f'/rag/chat/sessions/{identity}/messages?student_id={authz.STUDENT}'
        try:
            response = self.client.get(url, headers=self.headers())
        finally:
            event.remove(history_engine, 'before_cursor_execute', history_count)
            event.remove(authority_engine, 'before_cursor_execute', authority_count)
        self.assertEqual(response.status_code, 200, response.text)
        messages = response.json()['messages']
        self.assertEqual([row['content'] for row in messages], [f'Synthetic message {i}' for i in range(20)])
        self.assertEqual(sum(row['mode'] is not None for row in messages), 10)
        self.assertTrue(all(row['sources'] == [] for row in messages))
        with SessionLocal.begin() as db:
            db.query(MaterialShare).filter(MaterialShare.id == 6101).delete()
        self.assertEqual(self.client.get(url, headers=self.headers()).status_code, 404)
        print('HISTORY_QUERY_MEASUREMENT=' + json.dumps({'messages': 20, 'provenance_records': 10,
              'unchanged_output_and_revocation': True, **counts}, sort_keys=True))
        self.assertLessEqual(counts['history_selects'], 3)


if __name__ == '__main__':
    unittest.main()
