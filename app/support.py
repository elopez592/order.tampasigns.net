"""Single-use cross-origin platform support access, linked to its root session."""
import secrets
import time
from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse
from .db import transaction, audit
from .security import digest


def enrich(app, conn, session, user):
    if not hasattr(app.state,'support_root'): return user
    support=conn.execute('SELECT * FROM company_support_sessions WHERE token_hash=?',(session['token_hash'],)).fetchone()
    if not support: return user
    root=app.state.support_root
    with transaction(root.state.database) as source:
        valid=root.state.validate_support(source,support['root_session'],support['operator_email'],app.state.support_slug,app.state.support_hostname)
    if not valid: return None
    return dict(user,name='Platform support: '+support['operator_email'],email=support['operator_email'],
                support_company=app.state.support_slug,support_return=root.state.public_url+'/platform')


def install(app):
    db=app.state.database
    with transaction(db,True) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS company_support_sessions (token_hash TEXT PRIMARY KEY REFERENCES sessions(token_hash) ON DELETE CASCADE,root_session TEXT NOT NULL,operator_email TEXT NOT NULL)')

    @app.post('/api/auth/platform-support')
    def exchange(request:Request,payload:dict=Body(...)):
        root=getattr(app.state,'support_root',None)
        token=payload.get('token')
        if not root or not isinstance(token,str) or not 20<=len(token)<=200:
            raise HTTPException(401,'Support link is invalid or expired. Open Manage company again.')
        with transaction(root.state.database,True) as source:
            grant=source.execute('SELECT * FROM platform_support_grants WHERE token_hash=? AND expires_at>?',(digest(token),time.time())).fetchone()
            if (not grant or grant['slug']!=app.state.support_slug or grant['hostname']!=request.url.hostname
                or not root.state.validate_support(source,grant['root_session'],grant['operator_email'],grant['slug'],grant['hostname'])):
                raise HTTPException(401,'Support link is invalid or expired. Open Manage company again.')
            with transaction(db,True) as conn:
                owner=conn.execute("SELECT id,name,email,role FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
                if not owner: raise HTTPException(403,'Company has no active owner account.')
                conn.execute('DELETE FROM sessions WHERE token_hash=?',(request.state.session['token_hash'],))
                session_token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                conn.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',(digest(session_token),csrf,owner['id'],None,None,time.time()+3600))
                conn.execute('INSERT INTO company_support_sessions VALUES(?,?,?)',(digest(session_token),grant['root_session'],grant['operator_email']))
                audit(conn,None,grant['operator_email'],'platform.support_started',{'slug':grant['slug']})
            source.execute('DELETE FROM platform_support_grants WHERE token_hash=?',(digest(token),))
            audit(source,None,grant['operator_email'],'platform.support_started',{'slug':grant['slug']})
        response=JSONResponse({'ok':True,'csrf':csrf})
        response.set_cookie('signshop_session',session_token,httponly=True,secure=root.state.production,samesite='lax',max_age=3600,path='/')
        return response
