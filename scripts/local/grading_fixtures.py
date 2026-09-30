#!/usr/bin/env python3
"""Clone only named synthetic fixtures into new phase 3-A rows; no existing-row writes."""
import hashlib,json,re,uuid
from verify import sql,docker_exec
from manage import RESULTS
from grading_data import ident

def literal(value):return "'"+str(value).replace("'","''")+"'"
def columns(table):return [r.split('\t')[0] for r in sql('SHOW COLUMNS FROM '+ident(table)+';').splitlines() if not r.startswith('id\t')]
def clone_statement(table,where,replacements):
    cols=columns(table)
    return 'INSERT INTO '+ident(table)+' ('+','.join(map(ident,cols))+') SELECT '+','.join(replacements.get(c,ident(c)) for c in cols)+' FROM '+ident(table)+' WHERE '+where+';'
def clone_material(source,title,namespace="phase3a"):
    if namespace not in ("phase3a","phase3b"):raise ValueError("Unknown fixture phase")
    found=sql('SELECT id FROM materials WHERE title='+literal(title)+';')
    if found:return int(found)
    rows=sql(f'SELECT m.uploaded_file_id,f.jsons3key FROM materials m JOIN uploaded_files f ON f.id=m.uploaded_file_id WHERE m.id={int(source)};').split('\t')
    file_id,key=int(rows[0]),rows[1]
    newkey='local/synthetic/authz/'+namespace+'-'+str(uuid.uuid4())+'.json'
    if not re.fullmatch(r'local/synthetic/authz/[a-z0-9-]+\.json',key):raise RuntimeError('Only named synthetic AUTHZ object copies allowed')
    object_path=lambda k:'/app/local-data/objects/'+hashlib.sha256(k.encode()).hexdigest()+'.json'
    docker_exec('be',['cp',object_path(key),object_path(newkey)])
    statements=[clone_statement('uploaded_files',f'id={file_id}',{'jsons3key':literal(newkey),'s3key':literal(newkey),'concept_check_jsons3key':'NULL'}),'SET @new_file=LAST_INSERT_ID();',clone_statement('materials',f'id={int(source)}',{'title':literal(title),'uploaded_file_id':'@new_file'}),'SET @new_material=LAST_INSERT_ID();']
    for table in ('material_contents','quizzes','material_shares'):
        statements.append(clone_statement(table,f'material_id={int(source)}',{'material_id':'@new_material'}))
    statements.append('SELECT @new_material;')
    return int(sql('START TRANSACTION;\n'+'\n'.join(statements)+'\nCOMMIT;').splitlines()[-1])

def authz():
    rows=sql("SELECT id,title FROM materials WHERE title LIKE '[AUTHZ LOCAL] %' AND deleted_at IS NULL;")
    result={}
    for row in rows.splitlines():
        source,title=row.split('\t');suffix=title.removeprefix('[AUTHZ LOCAL] ')
        result[suffix]=clone_material(int(source),'[AUTHZ 3A] '+suffix)
    (RESULTS/'authorization-fixtures.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':print(json.dumps(authz()))
