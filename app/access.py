"""Restrictive employee profiles layered on existing owner/employee authorization."""
import re
from fastapi import Body, Depends, HTTPException
from .db import transaction, audit

PROFILES = {
 'employee': {'jobs','quotes','proofs','production','surveys','clients'},
 'sales': {'jobs','quotes','clients'},
 'designer': {'proofs'},
 'production': {'production'},
 'survey_install': {'surveys','production','clients'},
 'read_only': set(),
}


def permitted(app,user,path,method):
    if user['role']=='admin' or method in ('GET','HEAD','OPTIONS'): return True
    if not path.startswith(('/api/staff/','/api/admin/')): return True
    with transaction(app.state.database) as conn:
        row=conn.execute('SELECT profile FROM company_access WHERE user_id=?',(user['id'],)).fetchone()
    profile=row['profile'] if row else 'employee'
    if '/surveys' in path or '/panel-photos' in path: action='surveys'
    elif '/clients' in path: action='clients'
    elif '/proofs' in path or path.endswith('/layout'): action='proofs'
    elif '/tasks/' in path or path.endswith('/tasks'): action='production'
    elif '/estimates' in path or re.search(r'/(quote|publish|share|payment-link|invoices|online-price-correction)$',path): action='quotes'
    else: action='jobs'
    return action in PROFILES.get(profile,set())


def install(app,require_admin):
    db=app.state.database
    with transaction(db,True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS company_access(user_id INTEGER PRIMARY KEY REFERENCES users(id),profile TEXT NOT NULL DEFAULT 'employee')")

    @app.get('/api/admin/company/access')
    def access(user=Depends(require_admin)):
        with transaction(db) as conn:
            return {'profiles':list(PROFILES),'users':[dict(r) for r in conn.execute("SELECT u.id,u.name,u.email,u.role,u.active,COALESCE(a.profile,'employee') profile FROM users u LEFT JOIN company_access a ON a.user_id=u.id ORDER BY u.name")]}

    @app.put('/api/admin/company/access/{user_id}')
    def save(user_id:int,payload:dict=Body(...),user=Depends(require_admin)):
        profile=payload.get('profile')
        if profile not in PROFILES: raise HTTPException(422,'Select a staff profile.')
        with transaction(db,True) as conn:
            target=conn.execute('SELECT role FROM users WHERE id=?',(user_id,)).fetchone()
            if not target: raise HTTPException(404,'Staff member not found.')
            if target['role']=='admin': raise HTTPException(422,'Owners have full company access. Assign employee accounts a restricted profile.')
            conn.execute('INSERT INTO company_access VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET profile=excluded.profile',(user_id,profile))
            conn.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            audit(conn,None,user['email'],'staff.profile_updated',{'user_id':user_id,'profile':profile})
        return {'ok':True,'message':'Access updated. The staff member must sign in again.'}
