#!/usr/bin/env python3
"""Inspect names/state/network metadata only; never read another project's data."""
import json
import re
import subprocess
import sys
from manage import RESULTS, PROJECT, compose_args, clean_env, settings, snapshot
import scope_guard

snapshot('resources-after')
before=json.loads((RESULTS/'resources-before.json').read_text())
after=json.loads((RESULTS/'resources-after.json').read_text())
old_all={line.split('\t')[0]:line.split('\t')[1:] for line in before['containers']}
scope_guard.require('container_metadata' in before,'A fresh labelled before snapshot is required')
own_ids={r['id'][:12] for r in before['container_metadata'] if r['project']==PROJECT and r['service'] in scope_guard.SERVICES}
old={i:v for i,v in old_all.items() if i not in own_ids}
project_start={v[0]:v[1] for i,v in old_all.items() if i in own_ids}
new={line.split('\t')[0]:line.split('\t')[1:] for line in after['containers']}
after_own_ids={r['id'][:12] for r in after['container_metadata'] if r['project']==PROJECT and r['service'] in scope_guard.SERVICES}
external_after={i:v for i,v in new.items() if i not in after_own_ids}
external_added=[{'after_id':i,'name':v[0],'after_state':v[1]} for i,v in external_after.items() if i not in old]
new_by_name={v[0]:(identifier,v[1]) for identifier,v in new.items()}
external_identity_changes=[{'name':value[0],'before_id':identifier,
    'after_id':new_by_name.get(value[0],(None,None))[0],
    'before_state':value[1],'after_state':new_by_name.get(value[0],(None,None))[1]}
    for identifier,value in old.items() if identifier not in new]
checks={
 'external_id_set_unchanged':set(old)==set(external_after),
 'all_original_container_ids_preserved':all(i in new and new[i][0]==v[0] for i,v in old.items()),
 'original_running_states_preserved':all(i in new and (new[i][1]==v[1]) for i,v in old.items()),
 'all_original_volume_names_preserved':set(before['volumes']).issubset(after['volumes']),
 'all_original_network_names_preserved':set(before['networks']).issubset(after['networks']),
 'original_project_volumes_preserved':{n for n in before['volumes'] if n.startswith(PROJECT+'_')}.issubset(after['volumes']),
 'external_names_preserved':all(v[0] in new_by_name for v in old.values()),
 'external_states_by_name_preserved':all(new_by_name.get(v[0],(None,None))[1]==v[1] for v in old.values()),
}
def output(args): return subprocess.check_output(args,text=True).strip()
checks['application_network_internal']=output(['docker','network','inspect',PROJECT+'_default','--format','{{.Internal}}'])=='true'
names=output(['docker','ps','-a','--filter','label=com.docker.compose.project='+PROJECT,'--format','{{.Names}}']).splitlines()
networks={}; ports={}; states={}
for name in names:
    # Configured networks remain inspectable after stop. Published ports checked from HostConfig.
    networks[name]=json.loads(output(['docker','inspect',name,'--format','{{json .NetworkSettings.Networks}}']))
    ports[name]=json.loads(output(['docker','inspect',name,'--format','{{json .HostConfig.PortBindings}}'])) or {}
    states[name]=output(['docker','inspect',name,'--format','{{.State.Status}}'])
checks['only_nginx_on_gateway']=all(set(n)==({PROJECT+'_default',PROJECT+'_gateway'} if (name.endswith('-web-1') or name.endswith('-web-auth-test-1')) else {PROJECT+'_default'}) for name,n in networks.items())
checks['all_published_ports_loopback']=all(binding['HostIp']=='127.0.0.1' for p in ports.values() for binds in p.values() for binding in (binds or []))
checks['database_ports_unpublished']=all(not ports[n] for n in names if n.endswith(('-mysql-1','-redis-1','-chroma-1')))
logs=subprocess.run(compose_args('--profile','auth-test','logs','--no-color'),capture_output=True,text=True,env=clean_env())
checks['runtime_logs_readable']=logs.returncode==0
checks['runtime_logs_no_jwt']=not bool(re.search(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',logs.stdout))
checks['runtime_logs_no_generated_secret']=not any(v in logs.stdout for k,v in settings().items() if any(w in k for w in ('PASSWORD','SECRET')))
checks['project_start_states_restored']=all(states.get(name)==state for name,state in project_start.items())
checks['new_test_services_stopped']=all(state=='exited' for name,state in states.items() if name not in project_start)
from manage import ROOT, ENV_FILE
base=['docker','compose','--project-directory',str(ROOT),'--env-file',str(ENV_FILE),'-p',PROJECT,'-f',str(ROOT/'compose.local.yml')]
try:
    scope_guard.gate(['config','--quiet'],base,ROOT,clean_env(),RESULTS)
    target_scope='PASS'
except scope_guard.ScopeError:
    target_scope='BLOCKED'
checks['current_target_scope_validated']=target_scope=='PASS'
persistence=json.loads((RESULTS/'persistence-checks.json').read_text()) if (RESULTS/'persistence-checks.json').exists() else None
own_data=scope_guard.preservation_status(checks['original_project_volumes_preserved'],persistence)
result={'checks':checks,'CURRENT_MUTATION_SCOPE':target_scope,
        'CURRENT_EXTERNAL_ID_STABILITY':'PASS' if checks['external_id_set_unchanged'] and checks['all_original_container_ids_preserved'] and checks['original_running_states_preserved'] else 'FAIL',
        'EXTERNAL_CHANGE_ATTRIBUTION':'UNVERIFIED' if external_identity_changes or external_added or not checks['original_running_states_preserved'] else 'NOT_APPLICABLE',
        'OWN_DATA_PRESERVATION':own_data,
        'original_containers':len(old),'original_running':sum(v[1]=='running' for v in old.values()),'project_start_states':project_start,
        'external_identity_changes':external_identity_changes,
        'external_added_containers':external_added,
        'new_volumes':sorted(set(after['volumes'])-set(before['volumes'])),
        'new_networks':sorted(set(after['networks'])-set(before['networks'])),
        'project_containers':sorted(names),'states':states,'ports':ports}
(RESULTS/'resource-isolation-checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(0 if all(checks.values()) else 1)
