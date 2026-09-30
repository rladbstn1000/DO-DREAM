"""Fixed DO:DREAM target gate. It is not a general Docker administration API."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import datetime

PROJECT = 'dodream-phase1'
SERVICES = frozenset(('mysql','redis','be','be-test','ai','worker','python-service','web','be-auth-short','web-auth-test','chroma','index-dispatcher'))
MAIN = ('mysql','redis','be','ai','worker','python-service','web','chroma','index-dispatcher')
EXISTING_VOLUMES = frozenset(PROJECT+'_'+v for v in ('mysql-data','redis-data','be-data','ai-data'))
NEW_VOLUMES = frozenset((PROJECT+'_chroma-data',))
VOLUMES = EXISTING_VOLUMES | NEW_VOLUMES
NETWORKS = frozenset((PROJECT+'_default',PROJECT+'_gateway'))
MUTATIONS = frozenset(('build','up','start','stop','restart','run','exec'))
READS = frozenset(('config','ps','logs'))
RUN_LABEL = 'com.dodream.task=phase3b'
BUILD_CONTEXTS = {'be':'be','be-test':'be','ai':'ai','worker':'ai','web':'fe-web','python-service':'python-service','chroma':'scripts/local/chroma','index-dispatcher':'ai'}

class ScopeError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise ScopeError(message)


def preservation_status(volumes_preserved, persistence):
    if not volumes_preserved:return 'FAIL'
    if not persistence or not persistence.get('checks'):return 'NOT_RUN'
    statuses={r['status'] for r in persistence['checks']}
    if 'FAIL' in statuses:return 'FAIL'
    if 'BLOCKED' in statuses:return 'BLOCKED'
    return 'PASS' if statuses=={'PASS'} else 'NOT_RUN'


def port_available(port):
    # A closed connection's TIME_WAIT is not a live listener. REUSEADDR permits
    # that normal restart case, but never uses REUSEPORT to share a listener.
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:sock.bind(('127.0.0.1',port))
        except OSError:return False
        return True


def live_bind(source, destination, service, read_only, root):
    """Two fixed read-only files on the AI service; no generic secret mounts."""
    if service != 'ai' or not read_only or not root:
        return False
    source = Path(source)
    if source.is_symlink():
        return False
    pairs = {
        '/run/dodream-live/manifest.json': Path(root).resolve()/'.local/phase5/live/manifest.json',
        '/run/secrets/dodream-provider-live.env': Path.home()/'.config/dodream/provider-live.env',
    }
    return destination in pairs and source.absolute() == pairs[destination] and source.resolve() == pairs[destination]


def command_scope(args):
    """Parse only the small option vocabulary used by checked-in local scripts."""
    args=list(args); index=0; profiles=[]
    while index<len(args) and args[index].startswith('--'):
        flag=args[index];require(flag in ('--profile','--progress'),'Unknown Compose global option')
        require(index+1<len(args),'Missing Compose option value')
        if flag=='--profile':
            require(args[index+1] in ('test','auth-test'),'Unknown Compose profile');profiles.append(args[index+1])
        else: require(args[index+1]=='plain','Unsupported progress mode')
        index+=2
    require(index<len(args),'Missing Compose operation')
    operation=args[index];require(operation in MUTATIONS|READS,'Docker operation is not authorized')
    rest=args[index+1:]; targets=[]; i=0; fresh_schema=False
    no_value={'-d','--wait','--no-deps','--rm','-T','--all','--quiet','--no-color','--no-cache'}
    with_value={'--wait-timeout','--name','-e','--label','--format'}
    while i<len(rest):
        value=rest[i]
        if value.startswith('-'):
            require(value in no_value|with_value,'Unknown service option')
            if value in with_value:
                require(i+1<len(rest),'Missing service option value')
                parameter=rest[i+1]
                if value=='--name': require(bool(re.fullmatch(r'dodream-phase3[ab]-[a-z0-9-]+',parameter)),'One-off name is outside this task')
                if value=='-e':
                    if parameter in ('MYSQL_DATABASE=dodream_phase3a_fresh_v2','MYSQL_DATABASE=dodream_phase3b_fresh'):fresh_schema=parameter
                    else:require(parameter.split('=',1)[0] in ('JWT_SECRET','JWT_SECRET_BASE64'),'Unreviewed environment override')
                if value=='--label':require(parameter==RUN_LABEL,'Unknown one-off owner label')
                i+=2
            else:i+=1
            continue
        require(value in SERVICES,'Unknown or foreign Compose service')
        targets.append(value);i+=1
        if operation in ('exec','run'):
            payload=rest[i:]
            require(not any(re.search(r'\b(?:FLUSHALL|FLUSHDB|prune|system prune)\b',x,re.I) for x in payload),'Global deletion/reset command refused')
            break
    if operation in ('exec','run'): require(len(targets)==1,'Exactly one service required')
    if operation=='run':require('--rm' in rest and '--no-deps' in rest and '--name' in rest and '--label' in rest,'One-off run must be named, labelled and disposable')
    if fresh_schema:
        require(operation=='run' and targets==['be'] and '--name' in rest
                and rest[rest.index('--name')+1]==('dodream-phase3b-fresh-schema' if fresh_schema.endswith('phase3b_fresh') else 'dodream-phase3a-fresh-schema'),
                'Fresh schema override is restricted to its dedicated disposable Spring process')
    if not targets:
        targets=list(MAIN)
        if 'auth-test' in profiles:targets+=['be-auth-short','web-auth-test']
        if 'test' in profiles:targets+=['be-test']
    return operation,targets


def validate_plan(plan, root):
    require(plan.get('name')==PROJECT,'Unexpected Compose project')
    require(set(plan.get('services',{}))<=SERVICES,'Unexpected service in Compose file')
    require(plan.get('networks',{}).get('default',{}).get('internal') is True,'Application network must remain internal')
    for kind,allowed in (('volumes',VOLUMES),('networks',NETWORKS)):
        for value in plan.get(kind,{}).values():
            require(value.get('name') in allowed and not value.get('external'),'External/shared resource declaration refused')
    root=Path(root).resolve(); builds=set();ports=[]
    for name,service in plan['services'].items():
        require(not any(service.get(k) for k in ('privileged','network_mode','pid','ipc','devices','volumes_from','container_name')),'Unsafe container capability/name declaration')
        if 'build' in service:
            require(name in BUILD_CONTEXTS and Path(service['build']['context']).resolve()==root/BUILD_CONTEXTS[name],'Build context outside reviewed service')
            require(service['build'].get('dockerfile','Dockerfile')=='Dockerfile.local','Unreviewed Dockerfile')
            builds.add(service.get('image',PROJECT+'-'+name))
        image=service.get('image','')
        require(not image or image in ('mysql:8.4','redis:7.4-alpine',*(PROJECT+'-'+s for s in SERVICES)),'Unexpected service image')
        for mount in service.get('volumes',[]):
            if mount['type']=='volume':
                require(mount['source'] in ('mysql-data','redis-data','be-data','ai-data','chroma-data'),'Unexpected volume reference')
                if mount['source']=='chroma-data':require(name=='chroma' and mount.get('target')=='/chroma/chroma','Chroma storage belongs only to its server')
                if name=='chroma':require(mount['source']=='chroma-data','Chroma cannot mount existing application data')
            elif mount['type']=='bind':require(
                (Path(mount['source']).resolve()==root/'scripts/local/nginx.auth-test.conf' and mount.get('read_only') is True)
                or live_bind(mount['source'],mount.get('target'),name,mount.get('read_only'),root),'Unreviewed bind mount')
            else:raise ScopeError('Unreviewed mount type')
        live = name=='ai' and service.get('environment',{}).get('DODREAM_AI_MODE')=='LIVE_OPENAI'
        if live:
            require(str(service['environment'].get('LIVE_API_AUTHORIZED')).lower()=='true','Live authorization is not enabled')
            require({m.get('target') for m in service.get('volumes',[]) if m['type']=='bind'}=={'/run/dodream-live/manifest.json','/run/secrets/dodream-provider-live.env'},'Live configuration must have the two fixed mounts')
        elif name in ('ai','worker','index-dispatcher'):
            require(service.get('environment',{}).get('DODREAM_AI_MODE','LOCAL_FAKE')=='LOCAL_FAKE'
                and str(service.get('environment',{}).get('LIVE_API_AUTHORIZED','false')).lower()=='false'
                and not any(m['type']=='bind' for m in service.get('volumes',[])), 'Local runtime must stay keyless and unauthorized')
        require(set(service.get('networks',{}))<=({'default','gateway'} if name.startswith('web') or live else {'default'}),'Unexpected network membership')
        for port in service.get('ports',[]):
            require(port.get('host_ip')=='127.0.0.1' and name in ('web','web-auth-test'),'Only loopback nginx publishing is allowed')
            ports.append((name,int(port['published'])))
    return builds,ports


def validate_inventory(rows, build_images=(), root=None):
    owned=[r for r in rows if r['project']==PROJECT]
    for row in rows:
        if row['name'].startswith(PROJECT+'-'):require(row['project']==PROJECT,'Name collision with foreign project label')
        if row['project']==PROJECT:
            require(row['service'] in SERVICES,'Unknown service has our project label')
            require(set(row['networks'])<=NETWORKS,'Owned container attached to unexpected network')
            for m in row['mounts']:
                if m['type']=='volume':
                    require(m['name'] in VOLUMES,'Owned container uses unexpected volume')
                    if m['name'] in NEW_VOLUMES:require(row['service']=='chroma' and m['destination']=='/chroma/chroma','Shared Chroma filesystem refused')
                    if row['service']=='chroma':require(m['name'] in NEW_VOLUMES,'Chroma cannot mount existing application data')
                elif m['type']=='bind':require((root and Path(m['source']).resolve()==Path(root).resolve()/'scripts/local/nginx.auth-test.conf' and not m['rw'])
                    or live_bind(m['source'],m.get('destination'),row['service'],not m['rw'],root),'Owned container has an unreviewed bind')
                else:raise ScopeError('Owned container has an unreviewed mount type')
        else:
            require(not set(row['networks'])&NETWORKS,'Another project references our network')
            require(not any(m.get('name') in VOLUMES for m in row['mounts']),'Another project references our volume')
            require(row['image_tag'].removesuffix(':latest') not in build_images,'A build tag is used by another project')
            if root:
                require(not any(m['type']=='bind' and (Path(m['source']).resolve()==Path(root).resolve() or Path(root).resolve() in Path(m['source']).resolve().parents or Path(m['source']).resolve() in Path(root).resolve().parents) for m in row['mounts']),'Another project bind-mounts this workspace or an ancestor')
    return owned


def require_keyless_local(rows):
    ai=[row for row in rows if row['project']==PROJECT and row['service']=='ai']
    require(len(ai)==1 and not any(m['type']=='bind' for m in ai[0]['mounts'])
        and set(ai[0]['networks']) <= {PROJECT+'_default'},
        'Local regression refused while AI has live mounts or egress')


def read_metadata(env):
    ids=_read(['docker','ps','-a','--format','{{.ID}}'],env).splitlines()
    if not ids:return []
    # Deliberately excludes Env, Cmd, application logs and arbitrary label values.
    fmt='{{json .Id}}\t{{json .Name}}\t{{json .Created}}\t{{json .State.Status}}\t{{json .Config.Image}}\t{{json (index .Config.Labels "com.docker.compose.project")}}\t{{json (index .Config.Labels "com.docker.compose.service")}}\t{{json (index .Config.Labels "com.dodream.task")}}\t{{json .Mounts}}\t{{range $name, $value := .NetworkSettings.Networks}}{{$name}},{{end}}\t{{json .HostConfig.PortBindings}}'
    raw=_read(['docker','inspect','--format',fmt,*ids],env)
    result=[]
    for line in raw.splitlines():
        parts=line.split('\t');values=[json.loads(x) for x in parts[:9]]
        row=dict(zip(('id','name','created','state','image_tag','project','service','task','mounts'),values))
        row['name']=row['name'].lstrip('/');row['networks']=[x for x in parts[9].split(',') if x]
        row['ports']=json.loads(parts[10]) or {}
        row['mounts']=[{'type':m['Type'],'name':m.get('Name'),'source':m.get('Source'),'destination':m.get('Destination'),'rw':m.get('RW')} for m in row['mounts']]
        result.append(row)
    return result


def _read(args,env):
    result=subprocess.run(args,capture_output=True,text=True,env=env,timeout=20)
    require(result.returncode==0,'Docker metadata/config unavailable ('+' '.join(args[:2])+'; exit '+str(result.returncode)+'); mutations blocked')
    return result.stdout


def _gate(args,base,root,env):
    operation,targets=command_scope(args)
    endpoint=_read(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],env).strip()
    require(endpoint.startswith('unix://') and (not env.get('DOCKER_HOST') or env['DOCKER_HOST'].startswith('unix://')),'Remote Docker endpoints are forbidden')
    config=json.loads(_read([*base,'--profile','test','--profile','auth-test','config','--format','json'],env))
    builds,ports=validate_plan(config,root)
    # The four existing data volumes must never be silently replaced by a new project.
    for volume in sorted(EXISTING_VOLUMES):
        owner=_read(['docker','volume','inspect','--format','{{index .Labels "com.docker.compose.project"}}',volume],env).strip()
        require(owner==PROJECT,'Existing data volume ownership is unverified')
    existing_volumes=set(_read(['docker','volume','ls','--format','{{.Name}}'],env).splitlines())
    established=Path(root)/'.local'/'phase3b'/'chroma-volume-established.json'
    if established.exists():
        require(NEW_VOLUMES <= existing_volumes,'Established Chroma volume disappeared; never recreate it silently')
    for volume in sorted(NEW_VOLUMES & existing_volumes):
        owner=_read(['docker','volume','inspect','--format','{{index .Labels "com.docker.compose.project"}}',volume],env).strip()
        require(owner==PROJECT,'New Chroma volume name collides with an unverified owner')
        created=_read(['docker','volume','inspect','--format','{{.CreatedAt}}',volume],env).strip()
        if established.exists():
            require(json.loads(established.read_text())=={'name':volume,'created':created},'Established Chroma volume identity changed')
        else:
            established.parent.mkdir(parents=True,exist_ok=True)
            with established.open('x') as receipt:json.dump({'name':volume,'created':created},receipt)
    for network in sorted(NETWORKS):
        owner=_read(['docker','network','inspect','--format','{{index .Labels "com.docker.compose.project"}}',network],env).strip()
        require(owner==PROJECT,'Existing network ownership is unverified')
    rows=read_metadata(env);owned=validate_inventory(rows,builds,root)
    if operation=='exec' and targets==['ai'] and config['services']['ai'].get('environment',{}).get('DODREAM_AI_MODE','LOCAL_FAKE')=='LOCAL_FAKE':
        require_keyless_local(rows)
    if operation in ('exec','start','stop','restart'):
        require(set(targets)<={r['service'] for r in owned},'Target container not found with matching project/service labels')
    if operation in ('up','run'):
        used={int(binding['HostPort']) for r in owned if r['state']=='running' for bindings in r['ports'].values() for binding in (bindings or []) if binding['HostIp']=='127.0.0.1'}
        for service,port in ports:
            if service in targets and port not in used:
                require(port_available(port),'Loopback port '+str(port)+' unavailable; do not terminate the existing process')
    return {'status':'PASS','operation':operation,'project':PROJECT,'services':targets,'validated_containers':[{'id':r['id'],'service':r['service']} for r in owned], 'limits':'Target metadata only; no claim about unobserved direct or indirect effects.'}


def gate(args,base,root,env,results):
    try:
        report=_gate(args,base,root,env)
    except (ScopeError,subprocess.TimeoutExpired) as error:
        report={'status':'BLOCKED','project':PROJECT,'reason':str(error) if isinstance(error,ScopeError) else 'Metadata inspection timed out'}
        _record(report,results)
        raise ScopeError(report['reason']) from None
    _record(report,results)
    return report


def _record(report,results):
    report['observed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    Path(results).mkdir(parents=True,exist_ok=True)
    with (Path(results)/'mutation-scope.jsonl').open('a') as f:f.write(json.dumps(report)+'\n')


def crash_target(row, service):
    """Only the three task-owned processes used by observed 3-B crash gates."""
    require(service in ('be','worker','index-dispatcher'), 'Service is not a reviewed crash target')
    require(row and row['project']==PROJECT and row['service']==service and row['state']=='running', 'Crash target ownership/state unverified')
    require(row['name']==PROJECT+'-'+service+'-1', 'Only the primary owned service process may be crashed')
    return row['id']


def chroma_pause_target(row, resume=False):
    require(row and row['project']==PROJECT and row['service']=='chroma'
            and row['name']==PROJECT+'-chroma-1', 'Only the owned Chroma server may be paused')
    require(row['state']==('paused' if resume else 'running'), 'Unexpected Chroma pause state')
    return row['id']
