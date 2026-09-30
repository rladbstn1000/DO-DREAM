#!/usr/bin/env python3
"""Prepare four NEW authored copies through actual local publication APIs.

Generated synthetic visitor/refresh cookies stay in one ignored 0600 file; no
credentials enter reports or commands. No provider key is accessed here.
"""
import http.cookiejar
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import urllib.request
from datetime import datetime, timezone

from manage import ROOT, RESULTS
sys.path.insert(0,str(ROOT))
from scripts.evaluation.phase5 import load, validate, freeze, public_materials
from verify_student_demo import Client
from live_ai import LIVE, require

COOKIES = LIVE/'student.cookies.txt'


def student_client(create=False):
    LIVE.mkdir(parents=True,exist_ok=True)
    # exists() is false for a dangling link; CookieJar.save would otherwise
    # follow it when creating the session file and could overwrite its target.
    require(not COOKIES.is_symlink(),'STUDENT_SESSION_PERMISSIONS')
    exists=COOKIES.exists()
    require(exists or create,'SYNTHETIC_STUDENT_SESSION_REQUIRED')
    from verify import BASE, NoRedirect
    client=Client(BASE,NoRedirect)
    client.jar=http.cookiejar.MozillaCookieJar(str(COOKIES))
    if exists:
        require(COOKIES.is_file() and not COOKIES.is_symlink() and stat.S_IMODE(COOKIES.stat().st_mode)==0o600,'STUDENT_SESSION_PERMISSIONS')
        client.jar.load(ignore_discard=True,ignore_expires=True)
    client.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPCookieProcessor(client.jar))
    code,data,_=client.call('/api/auth/csrf')
    require(code==200,'LOCAL_CSRF_UNAVAILABLE');client.csrf=data
    if exists:
        code,data,_=client.auth('/api/auth/student/refresh')
        require(code==200,'EXISTING_STUDENT_REFRESH_REQUIRED')
    else:
        code,_,_=client.auth('/api/auth/demo/bootstrap')
        require(code==200,'LOCAL_VISITOR_BOOTSTRAP_FAILED')
        code,data,_=client.auth('/api/auth/demo/start')
        require(code==200,'LOCAL_STUDENT_START_FAILED')
    require(isinstance(data,dict) and isinstance(data.get('accessToken'),str),'LOCAL_STUDENT_AUTH_FAILED')
    client.token=data['accessToken']
    code,user,_=client.call('/api/session/me',token=client.token)
    require(code==200 and user.get('role')=='STUDENT' and user.get('demo') is True,'SYNTHETIC_STUDENT_REQUIRED')
    client.user=user
    # CookieJar.save uses mode 0600 for a new file. Existing mode checked above.
    client.jar.save(ignore_discard=True,ignore_expires=True)
    os.chmod(COOKIES,0o600)
    return client


def validate_prepared_response(data,bundle,student_id):
    """Bind the running server's complete authored fixture, including quizzes."""
    resource=ROOT/'be/src/main/resources/demo/phase5-materials.json'
    require(isinstance(data,dict) and data.get('status')=='PASS'
        and data.get('fixture_version')=='phase5-eval-v1'
        and data.get('resource_sha256')==hashlib.sha256(resource.read_bytes()).hexdigest(),
        'PREPARED_SERVER_RESOURCE_MISMATCH')
    expected={m['material_key']:m for m in public_materials(bundle)}
    materials=data.get('materials')
    require(type(materials) is list and len(materials)==4
        and all(type(m) is dict and type(m.get('material_id')) is int and m['material_id']>0 for m in materials)
        and len({m['material_id'] for m in materials})==4
        and {m.get('material_key') for m in materials}==set(expected),'FOUR_NEW_MATERIALS_REQUIRED')
    for material in materials:
        fixed=expected[material['material_key']]
        require(material.get('source_hash')==fixed['source_hash']
            and material.get('spec')=='openai-text-embedding-3-small-1536-l2-content-v1'
            and type(material.get('source_revision')) is int and material['source_revision']>0
            and type(material.get('user_ids')) is list and student_id in material['user_ids'],
            'AUTHORED_SOURCE_BINDING_FAILED')
    return materials


def prepare():
    from student_demo_prepare import EMAIL
    from verify import ENV, req
    bundle=load();validate(bundle);frozen=freeze()
    code,config,_,_=req('be','/api/auth/demo/config')
    require(code==200 and config.get('enabled') and config.get('ready'),'LOCAL_DEMO_PREPARATION_REQUIRED')
    code,login,_,_=req('be','/api/auth/teacher/login',body={'email':EMAIL,'password':ENV['LOCAL_TEACHER_PASSWORD']})
    require(code==200 and login.get('accessToken'),'DEDICATED_TEACHER_LOGIN_FAILED')
    created_student=not COOKIES.exists()
    student=student_client(create=True)
    code,mode,_=student.call('/rag/mode',token=student.token,service='ai')
    require(code==200 and mode.get('configured_mode')=='LOCAL_FAKE','PREPARE_REQUIRES_KEYLESS_LOCAL_MODE')
    code,data,_,_=req('be','/api/demo/phase5/prepare',login['accessToken'],{'studentId':student.user['userId']},timeout=90)
    require(code==200 and isinstance(data,dict),'PHASE5_PREPARATION_FAILED')
    materials=validate_prepared_response(data,bundle,student.user['userId'])
    receipt={'status':'PASS','scope':'local_publication_only_live_index_queued',
        'dataset_sha256':frozen['dataset_sha256'],'student_id':student.user['userId'],
        'materials':materials,'provider_requests':0,'observed_at':datetime.now(timezone.utc).isoformat()}
    target=RESULTS/'phase5-prepared.json'
    if target.exists():
        old=json.loads(target.read_text())
        require(old['dataset_sha256']==receipt['dataset_sha256'] and old['materials']==receipt['materials']
            and old['student_id']==receipt['student_id'],'PREPARATION_REPLAY_MISMATCH')
    else:
        with target.open('x') as stream:json.dump(receipt,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'status':'PASS','new_materials':4,'new_evaluation_student':created_student,
        'provider_requests':0,'receipt':str(target),'live_embedding':'NOT_RUN'}))

if __name__=='__main__':
    try:prepare()
    except Exception as error:
        print(json.dumps({'status':'BLOCKED','reason':str(error) if isinstance(error,RuntimeError) else type(error).__name__}))
        raise SystemExit(2)
