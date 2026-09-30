#!/usr/bin/env python3
"""Phase 2-A real Spring/FastAPI + real Redis regression. Never persist credentials/tokens."""
import base64
import concurrent.futures
import hashlib
import hmac
import http.cookiejar
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from manage import RESULTS, settings, compose_args, clean_env

ENV=settings()
URL={'be':'http://127.0.0.1:'+ENV['BE_PORT'],'ai':'http://127.0.0.1:'+ENV['AI_PORT'],'web':'http://127.0.0.1:'+ENV['WEB_PORT']}
KEY=base64.b64decode(ENV['JWT_SECRET_BASE64'])
CHECKS=[]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class Client:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf=None
    def call(self,path,method='GET',body=None,token=None,headers=None,service='be'):
        h={'Content-Type':'application/json'}
        if token: h['Authorization']='Bearer '+token
        if headers: h.update(headers)
        r=urllib.request.Request(URL[service]+path,method=method,headers=h,data=None if body is None else json.dumps(body).encode())
        try: response=self.opener.open(r,timeout=15)
        except urllib.error.HTTPError as e: response=e
        raw=response.read()
        try: data=json.loads(raw)
        except (ValueError,UnicodeDecodeError): data=None
        return response.status,data,response.headers
    def bootstrap(self):
        code,data,_=self.call('/api/auth/csrf')
        if code!=200:raise RuntimeError('csrf prerequisite')
        self.csrf=data
    def auth(self,path,body=None,token=None):
        if not self.csrf:self.bootstrap()
        return self.call(path,'POST',{} if body is None else body,token,{self.csrf['headerName']:self.csrf['token']})
    def login(self):
        code,data,headers=self.auth('/api/auth/teacher/login',{'email':'other-teacher@local.dodream.invalid','password':ENV['LOCAL_TEACHER_PASSWORD']})
        if code!=200:raise RuntimeError('synthetic teacher login prerequisite')
        return data['accessToken'],self.cookie('refresh'),headers
    def cookie(self,name):
        return next((c.value for c in self.jar if c.name==name),None)
    def replace_refresh(self,value):
        for c in list(self.jar):
            if c.name=='refresh':c.value=value


def record(name,ok,detail=''):
    row={'name':name,'status':'PASS' if ok else 'FAIL','detail':detail}
    CHECKS.append(row);print(json.dumps(row))

def blocked(name,detail):
    row={'name':name,'status':'BLOCKED','detail':detail}
    CHECKS.append(row);print(json.dumps(row))

def has_token(data,name='accessToken'):
    return isinstance(data,dict) and isinstance(data.get(name),str) and bool(data[name])

def decode(token):return json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'='*(-len(token.split('.')[1])%4)))
def b64(data):return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
def sign(claims,alg='HS256',key=KEY,raw_payload=None):
    head=b64(json.dumps({'alg':alg,'typ':'JWT'},separators=(',',':')).encode())
    body=b64((raw_payload if raw_payload is not None else json.dumps(claims,separators=(',',':'))).encode())
    digest=hashlib.sha512 if alg=='HS512' else hashlib.sha256
    return head+'.'+body+'.'+b64(hmac.new(key,(head+'.'+body).encode(),digest).digest())

def expect_rejected(name,token):
    for service,path in [('be','/api/teacher/me'),('ai','/users/users/me')]:
        code,_,_=Client().call(path,token=token,service=service)
        record('token_'+name+'_'+service,code==401,'HTTP '+str(code))

def token_contract():
    c=Client();at,rt,_=c.login();a=decode(at);r=decode(rt)
    for svc,path in [('be','/api/teacher/me'),('ai','/users/users/me')]:
        code,_,_=c.call(path,token=at,service=svc);record('valid_access_'+svc,code==200,'HTTP '+str(code))
    record('configured_access_lifetime',a['exp']-a['iat']==900,'observed seconds='+str(a['exp']-a['iat']))
    record('configured_refresh_lifetime',r['exp']-r['iat']==1209600,'observed seconds='+str(r['exp']-r['iat']))
    expect_rejected('refresh_as_access',rt)
    c.replace_refresh(at);code,data,_=c.auth('/api/auth/teacher/refresh')
    record('access_as_refresh_rejected',code==401 and not (data or {}).get('accessToken'),'HTTP '+str(code))
    variants={
        'legacy_no_kind':{k:v for k,v in a.items() if k!='token_use'},
        'issuer':{**a,'iss':'incorrect-issuer'},'audience':{**a,'aud':'incorrect-audience'},
        'audience_multi':{**a,'aud':['dodream-api','unexpected']},
        'expired':{**a,'iat':a['iat']-120,'nbf':a['nbf']-120,'exp':a['iat']-30},
        'future_iat':{**a,'iat':a['iat']+60,'nbf':a['nbf']+60,'exp':a['exp']+60},
        'future_nbf':{**a,'nbf':a['nbf']+60},'excess_lifetime':{**a,'exp':a['iat']+901},
        'kind_unknown':{**a,'token_use':'unknown'},'sub_zero':{**a,'sub':'0'},
        'sub_numeric':{**a,'sub':int(a['sub'])},'sub_leading_zero':{**a,'sub':'0'+a['sub']},
        'sub_overflow':{**a,'sub':str(2**63)},'jti_invalid':{**a,'jti':'not-a-uuid'},
        'jti_upper':{**a,'jti':a['jti'].upper()},'role_unknown':{**a,'role':'ADMIN'},
        'exp_string':{**a,'exp':str(a['exp'])},'exp_float':{**a,'exp':a['exp']+0.5},
        'iat_bool':{**a,'iat':True},'nbf_negative':{**a,'nbf':-1},
        'name_wrong_type':{**a,'name':123},'name_blank':{**a,'name':' '},
    }
    for key in ('sub','jti','role','iss','aud','iat','nbf','exp','token_use'):
        variants['missing_'+key]={k:v for k,v in a.items() if k!=key}
    for name,claims in variants.items():expect_rejected(name,sign(claims))
    expect_rejected('wrong_signature',sign(a,key=secrets.token_bytes(32)))
    expect_rejected('wrong_algorithm',sign(a,alg='HS512'))
    expect_rejected('unsigned_none',b64(b'{"alg":"none"}')+'.'+b64(json.dumps(a).encode())+'.')
    raw=json.dumps(a)[:-1]+',"sub":"'+a['sub']+'"}'
    expect_rejected('duplicate_claim',sign(a,raw_payload=raw))
    # This signed 12KB Authorization header is rejected before either application
    # by nginx's HTTP header limit. Keep a strict transport assertion separately
    # from signed-oversize JwtUtil/decode_access_token unit coverage.
    oversized=sign({**a,'name':'x'*9000})
    for service,path in [('be','/api/teacher/me'),('ai','/users/users/me')]:
        code,data,headers=Client().call(path,token=oversized,service=service)
        record('token_oversized_'+service,code==400 and headers.get('Server','').startswith('nginx/')
               and not (isinstance(data,dict) and data.get('accessToken')),
               'HTTP '+str(code)+'; nginx header boundary; signed oversized validator covered separately')
    # Same-second uniqueness is observed, not assumed from quick execution.
    tokens=[]
    for _ in range(8):
        _,refresh,_=Client().login();tokens.append(refresh)
    buckets={}
    for token in tokens:buckets.setdefault(decode(token)['iat'],[]).append(token)
    same=max(buckets.values(),key=len)
    record('same_second_refresh_unique',len(same)>=2 and len(set(same))==len(same),'same-second issues='+str(len(same)))
    c=Client();at,rt,_=c.login()
    expired={**decode(at),'iat':int(time.time())-120,'nbf':int(time.time())-120,'exp':int(time.time())-30}
    code,data,_=c.auth('/api/auth/teacher/refresh',token=sign(expired))
    record('expired_access_does_not_block_refresh',code==200 and bool(data.get('accessToken')),'HTTP '+str(code))

def redis(*args):
    result=subprocess.run(compose_args('exec','-T','redis','redis-cli','--raw',*args),capture_output=True,text=True,env=clean_env())
    if result.returncode:raise RuntimeError('redis command failure')
    return result.stdout.strip()

def refresh_with(rt,at=None):
    client=Client();client.bootstrap()
    return client.call('/api/auth/teacher/refresh','POST',{},at,{
        client.csrf['headerName']:client.csrf['token'],
        'Cookie':'refresh='+rt+'; '+ '; '.join(c.name+'='+c.value for c in client.jar)})

def native(body,path='refresh'):
    return Client().call('/api/auth/student/native/'+path,'POST',body)

def rotation():
    c=Client();at,rt,_=c.login();uid=decode(rt)['sub'];key='refresh:v2:'+uid
    stored=redis('GET',key)
    record('redis_stores_digest_not_raw',stored==hashlib.sha256(rt.encode()).hexdigest() and stored!=rt,'sha256 matching, values omitted')
    ttl=int(redis('TTL',key));expected=decode(rt)['exp']-int(time.time())
    record('redis_ttl_matches_expiry',0<=expected-ttl<=2,'ttl delta seconds='+str(expected-ttl))
    code,data,headers=c.auth('/api/auth/teacher/refresh');new=c.cookie('refresh')
    record('sequential_rotation',code==200 and has_token(data) and isinstance(new,str) and bool(new) and new!=rt,'HTTP '+str(code))
    code,data,headers=refresh_with(rt)
    record('rotated_token_reuse_rejected',code==401,'HTTP '+str(code))
    record('loser_does_not_clear_cookie',not headers.get('Set-Cookie'),'no cookie mutation in rejected refresh')
    record('loser_preserves_winner_hash',redis('GET',key)==hashlib.sha256(new.encode()).hexdigest(),'digest only compared in memory')
    # These keys belong exclusively to the synthetic second teacher account.
    redis('DEL',key)
    code,_,_=refresh_with(new);record('missing_session_denied',code==401,'HTTP '+str(code))
    c=Client();_,rt,_=c.login();redis('EXPIRE',key,'1');time.sleep(1.2)
    code,_,_=refresh_with(rt);record('expired_redis_session_denied',code==401,'HTTP '+str(code))
    for roundno in range(3):
        _,rt,_=Client().login();barrier=threading.Barrier(12)
        def race(_):
            client=Client();client.bootstrap()
            headers={client.csrf['headerName']:client.csrf['token'],'Cookie':'refresh='+rt+'; '+ '; '.join(c.name+'='+c.value for c in client.jar)}
            barrier.wait(timeout=15)
            return client.call('/api/auth/teacher/refresh','POST',{},headers=headers)
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(race,range(12)))
        codes=[r[0] for r in results]
        record('parallel_rotation_round_'+str(roundno+1),codes.count(200)==1 and codes.count(401)==11,'12 independent clients: 200='+str(codes.count(200))+'; 401='+str(codes.count(401)))
        record('parallel_losers_do_not_clear_cookie_'+str(roundno+1),all(not r[2].get('Set-Cookie') for r in results if r[0]==401) and codes.count(401)==11,'all rejected clients leave the winner cookie intact')
        winner=next((r for r in results if r[0]==200),None)
        if winner:
            import http.cookies
            jar=http.cookies.SimpleCookie();jar.load(winner[2].get('Set-Cookie',''))
            winning_rt=jar['refresh'].value
            record('parallel_winner_preserved_'+str(roundno+1),has_token(winner[1]) and bool(winning_rt) and redis('GET',key)==hashlib.sha256(winning_rt.encode()).hexdigest(),'late losers cannot overwrite state')
        else:
            blocked('parallel_winner_preserved_'+str(roundno+1),'No successful refresh response to validate')
    # User-wide logout with a cryptographically valid refresh revokes the current single session.
    for roundno in range(3):
        _,rt,_=Client().login();barrier=threading.Barrier(2)
        def operation(path):
            client=Client();client.bootstrap();h={client.csrf['headerName']:client.csrf['token'],'Cookie':'refresh='+rt+'; '+ '; '.join(c.name+'='+c.value for c in client.jar)}
            barrier.wait(timeout=15)
            return client.call('/api/auth/teacher/'+path,'POST',{},headers=h)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            fs=[pool.submit(operation,p) for p in ('refresh','logout')];results=[f.result() for f in fs]
        code,_,_=refresh_with(rt)
        record('logout_refresh_race_'+str(roundno+1),results[1][0] in (200,204) and results[0][0] in (200,401) and code==401 and redis('EXISTS',key)=='0','logout='+str(results[1][0])+'; old refresh='+str(code)+'; no session')
        if results[0][0]==200:
            import http.cookies
            jar=http.cookies.SimpleCookie();jar.load(results[0][2].get('Set-Cookie',''))
            record('logout_race_new_refresh_revoked_'+str(roundno+1),has_token(results[0][1]) and refresh_with(jar['refresh'].value)[0]==401,'newly rotated credential cannot revive the session')
    c=Client();at,rt,_=c.login();code,_,headers=c.auth('/api/auth/teacher/logout')
    record('logout_revokes_refresh',code in (200,204) and refresh_with(rt)[0]==401,'HTTP '+str(code))
    record('access_remains_valid_until_expiry',Client().call('/api/teacher/me',token=at)[0]==200,'no access-token denylist is claimed')
    _,rt,_=Client().login()
    first=refresh_with(rt)  # Simulate a client losing/ignoring the successful response.
    record('lost_response_old_token_not_reaccepted',first[0]==200 and refresh_with(rt)[0]==401,'simulated discarded response; re-login required')
    # Native transport is explicit token body, with no ambient cookies.
    code,data,headers=native({'deviceId':'dodream-local-student','deviceSecret':ENV['LOCAL_STUDENT_SECRET']},'login')
    record('native_login_transport',code==200 and has_token(data) and has_token(data,'refreshToken') and not headers.get('Set-Cookie'),'HTTP '+str(code)+'; no cookie')
    if code==200 and has_token(data) and has_token(data,'refreshToken'):
        nrt=data['refreshToken'];code,data,headers=native({'refreshToken':nrt})
        record('native_rotation',code==200 and has_token(data) and has_token(data,'refreshToken') and data['refreshToken']!=nrt and not headers.get('Set-Cookie'),'HTTP '+str(code))
        record('native_old_refresh_rejected',native({'refreshToken':nrt})[0]==401)
        if code==200 and has_token(data) and has_token(data,'refreshToken'):
            nrt=data['refreshToken'];code,_,_=native({'refreshToken':nrt},'logout')
            record('native_logout',code in (200,204) and native({'refreshToken':nrt})[0]==401)
        else:
            blocked('native_logout','Native rotation did not return a usable token pair')
    else:
        for check in ('native_rotation','native_old_refresh_rejected','native_logout'):
            blocked(check,'Native login did not return a usable token pair')


def csrf_cookie():
    c=Client();at,rt,headers=c.login();cookies=headers.get_all('Set-Cookie',[])
    rc=next((v for v in cookies if v.startswith('refresh=')), '')
    record('local_refresh_cookie_attributes','HttpOnly' in rc and 'Path=/api/auth' in rc and 'SameSite=Lax' in rc and 'Secure' not in rc,'local HTTP exception only')
    for path in ('login','refresh','logout'):
        body={'email':'other-teacher@local.dodream.invalid','password':ENV['LOCAL_TEACHER_PASSWORD']} if path=='login' else {}
        code,_,_=c.call('/api/auth/teacher/'+path,'POST',body)
        record('csrf_missing_'+path,code==403,'HTTP '+str(code))
        code,_,_=c.call('/api/auth/teacher/'+path,'POST',body,headers={c.csrf['headerName']:'incorrect'})
        record('csrf_wrong_'+path,code==403,'HTTP '+str(code))
    for role in ('teacher', 'student'):
        for action in ('login', 'refresh', 'logout'):
            encoded = '%' + format(ord(action[0]), '02x') + action[1:]
            code,_,_=c.call('/api/auth/'+role+'/'+encoded, 'POST', {})
            record('csrf_encoded_'+role+'_'+action, code==403, 'HTTP '+str(code)+'; decoded route remains protected')
    code,_,_=c.call('/api/auth/teacher/refresh','POST',{},headers={'X-Platform':'native'})
    record('platform_header_no_csrf_bypass',code==403,'HTTP '+str(code)+'; no Origin so CORS cannot mask this check')
    code,_,_=c.call('/api/auth/teacher/refresh','POST',{},headers={'Origin':'https://untrusted.invalid',c.csrf['headerName']:c.csrf['token']})
    record('untrusted_origin_rejected',code==403,'HTTP '+str(code))
    code,data,headers=c.auth('/api/auth/teacher/refresh')
    record('csrf_legitimate_refresh',code==200 and 'refreshToken' not in (data or {}),'HTTP '+str(code)+'; refresh excluded from browser body')
    code,data,_=c.auth('/api/auth/teacher/%72efresh')
    record('csrf_encoded_legitimate_refresh',code==200 and bool((data or {}).get('accessToken')),'HTTP '+str(code))
    code,_,headers=c.auth('/api/auth/teacher/logout')
    deletion=next((v for v in headers.get_all('Set-Cookie',[]) if v.startswith('refresh=')), '')
    record('cookie_logout_deletion',code in (200,204) and 'Max-Age=0' in deletion and 'Path=/api/auth' in deletion and 'HttpOnly' in deletion and 'SameSite=Lax' in deletion,'same path and flags, zero age')


def redis_failure():
    c=Client();at,rt,_=c.login()
    stopped=False
    try:
        result=subprocess.run(compose_args('stop','redis'),capture_output=True,text=True,env=clean_env())
        if result.returncode:raise RuntimeError('stop test redis')
        stopped=True
        for action in ('login','refresh','logout'):
            body={'email':'other-teacher@local.dodream.invalid','password':ENV['LOCAL_TEACHER_PASSWORD']} if action=='login' else {}
            code,data,headers=c.auth('/api/auth/teacher/'+action,body)
            record('redis_failure_'+action,code==503 and not (data or {}).get('accessToken') and not headers.get('Set-Cookie'),'HTTP '+str(code)+'; no token/session-success/cookie mutation')
        wrong=Client();wrong.bootstrap();code,_,_=wrong.auth('/api/auth/teacher/login',{'email':'other-teacher@local.dodream.invalid','password':'incorrect-local-only'})
        record('invalid_credentials_distinct_from_redis_failure',code==401,'HTTP '+str(code))
    finally:
        if stopped:
            result=subprocess.run(compose_args('start','redis'),capture_output=True,text=True,env=clean_env())
            if result.returncode:raise RuntimeError('restore test redis')
            for _ in range(30):
                try:
                    if redis('PING')=='PONG':break
                except RuntimeError:pass
                time.sleep(.5)
            else: raise RuntimeError('Redis recovery timeout')
    # Preserve data, then revoke only the test account's current refresh state.
    code,_,_=c.auth('/api/auth/teacher/logout')
    record('redis_recovered_logout',code in (200,204),'HTTP '+str(code))


def main():
    for name,operation in [('token_contract',token_contract),('rotation',rotation),('csrf_cookie',csrf_cookie),('redis_failure',redis_failure)]:
        try:operation()
        except Exception as e:
            CHECKS.append({'name':name,'status':'BLOCKED','detail':type(e).__name__})
            print(name,'BLOCKED',type(e).__name__)
    output={'checks':CHECKS,'counts':{s:sum(r['status']==s for r in CHECKS) for s in ('PASS','FAIL','BLOCKED','NOT_RUN')},'total':len(CHECKS)}
    (RESULTS/'auth-checks.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output['counts']))
    return int(any(r['status'] in ('FAIL','BLOCKED') for r in CHECKS))
if __name__=='__main__':sys.exit(main())
