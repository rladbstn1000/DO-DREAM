#!/usr/bin/env python3
"""Inspect names/state/network metadata only; never read another project's data."""
import json
import re
import subprocess
import sys
from manage import RESULTS, PROJECT, compose_args, clean_env, settings, snapshot

snapshot('resources-after')
before=json.loads((RESULTS/'resources-before.json').read_text())
after=json.loads((RESULTS/'resources-after.json').read_text())
old={line.split('\t')[0]:line.split('\t')[1:] for line in before['containers']}
new={line.split('\t')[0]:line.split('\t')[1:] for line in after['containers']}
checks={
 'all_original_container_ids_preserved':all(i in new and new[i][0]==v[0] for i,v in old.items()),
 'original_running_states_preserved':all(i in new and (new[i][1].startswith('Up')==v[1].startswith('Up')) for i,v in old.items()),
 'all_original_volume_names_preserved':set(before['volumes']).issubset(after['volumes']),
 'all_original_network_names_preserved':set(before['networks']).issubset(after['networks']),
 'no_preexisting_phase1_volumes':not any(n.startswith(PROJECT+'_') for n in before['volumes']),
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
checks['only_nginx_on_gateway']=all(set(n)==({PROJECT+'_default',PROJECT+'_gateway'} if name.endswith('-web-1') else {PROJECT+'_default'}) for name,n in networks.items())
checks['all_published_ports_loopback']=all(binding['HostIp']=='127.0.0.1' for p in ports.values() for binds in p.values() for binding in (binds or []))
checks['database_ports_unpublished']=all(not ports[n] for n in names if n.endswith(('-mysql-1','-redis-1')))
logs=subprocess.run(compose_args('logs','--no-color'),capture_output=True,text=True,env=clean_env())
checks['runtime_logs_readable']=logs.returncode==0
checks['runtime_logs_no_jwt']=not bool(re.search(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',logs.stdout))
checks['runtime_logs_no_generated_secret']=not any(v in logs.stdout for k,v in settings().items() if any(w in k for w in ('PASSWORD','SECRET')))
result={'checks':checks,'original_containers':len(old),'original_running':sum(v[1].startswith('Up') for v in old.values()),
        'new_volumes':sorted(set(after['volumes'])-set(before['volumes'])),
        'new_networks':sorted(set(after['networks'])-set(before['networks'])),
        'project_containers':sorted(names),'states':states,'ports':ports}
(RESULTS/'resource-isolation-checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(0 if all(checks.values()) else 1)
