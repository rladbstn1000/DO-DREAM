"""Fixture identity/cookie safeguards without Docker, secrets or HTTP calls."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import phase5_prepare as preparation


class Phase5PreparationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=preparation.load()

    def response(self):
        materials=[]
        for number,source in enumerate(preparation.public_materials(self.bundle),1):
            materials.append({'material_key':source['material_key'],'material_id':number,
                'source_hash':source['source_hash'],'source_revision':1,'user_ids':[10,20],
                'spec':'openai-text-embedding-3-small-1536-l2-content-v1'})
        path=preparation.ROOT/'be/src/main/resources/demo/phase5-materials.json'
        return {'status':'PASS','fixture_version':'phase5-eval-v1',
            'resource_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'materials':materials}

    def test_running_server_resource_and_all_four_fixed_materials_match(self):
        data=self.response()
        self.assertEqual(data['materials'],preparation.validate_prepared_response(data,self.bundle,20))

    def test_stale_server_fixture_or_nonpassing_result_is_rejected(self):
        for field,value in [('resource_sha256','0'*64),('fixture_version','older-fixture'),('status','PARTIAL')]:
            data=self.response();data[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'PREPARED_SERVER_RESOURCE_MISMATCH'):
                preparation.validate_prepared_response(data,self.bundle,20)

    def test_four_ids_cannot_hide_duplicate_or_missing_material_key(self):
        data=self.response();data['materials'][1]['material_key']=data['materials'][0]['material_key']
        with self.assertRaisesRegex(RuntimeError,'FOUR_NEW_MATERIALS_REQUIRED'):
            preparation.validate_prepared_response(data,self.bundle,20)

    def test_reused_or_boolean_material_ids_are_rejected(self):
        for value in (1,True):
            data=self.response();data['materials'][1]['material_id']=value
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'FOUR_NEW_MATERIALS_REQUIRED'):
                preparation.validate_prepared_response(data,self.bundle,20)

    def test_wrong_source_revision_spec_or_student_cannot_bind_scope(self):
        for field,value in [('source_hash','0'*64),('source_revision',True),('spec','local-hash8-content-v1'),('user_ids',[10])]:
            data=self.response();data['materials'][0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'AUTHORED_SOURCE_BINDING_FAILED'):
                preparation.validate_prepared_response(data,self.bundle,20)

    def test_dangling_session_symlink_rejected_before_client_or_file_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/'must-not-be-created';cookies=root/'student.cookies.txt'
            cookies.symlink_to(target)
            with patch.object(preparation,'LIVE',root),patch.object(preparation,'COOKIES',cookies),patch.object(preparation,'Client') as client:
                with self.assertRaisesRegex(RuntimeError,'STUDENT_SESSION_PERMISSIONS'):
                    preparation.student_client(create=True)
                client.assert_not_called()
            self.assertFalse(target.exists());self.assertTrue(cookies.is_symlink())


if __name__=='__main__':unittest.main()
