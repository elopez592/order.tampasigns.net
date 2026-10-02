"""Apply an authorized, bundled company setup once to its existing workspace."""
import hashlib
import json
import re
from pathlib import Path
from .company import FIELDS, DEFAULTS, record_revision, validate
from .db import transaction, settings, audit, now
from .images import sanitize
from .pricing import validate_config


def apply_icon_update(conn, brand, bundle, setup):
    update=setup.get('icon_update')
    if not update or conn.execute('SELECT 1 FROM company_setup_applied WHERE id=?',(update['id'],)).fetchone():
        return
    clean,_,_,_=sanitize((bundle/update['image']).read_bytes(),update['image'])
    filename=hashlib.sha256(clean).hexdigest()+'.png'
    (brand/filename).write_bytes(clean)
    (brand/filename).chmod(0o600)
    shop=settings(conn)|{'brand_icon':filename}
    draft=json.loads(conn.execute('SELECT data FROM company_draft WHERE id=1').fetchone()[0])|{'brand_icon':filename}
    conn.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(shop),))
    conn.execute('UPDATE company_draft SET data=?,version=version+1,updated_at=? WHERE id=1',(json.dumps(draft),now()))
    record_revision(conn,shop,'Platform owner',update['note'])
    audit(conn,None,'Platform owner','company.icon_updated',{'id':update['id']})
    conn.execute('INSERT INTO company_setup_applied VALUES(?,?)',(update['id'],now()))


def apply_setup(app, company):
    slug=company['slug']
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,39}',slug):
        return
    bundle=Path(__file__).parent/'company_setups'/slug
    manifest=bundle/'setup.json'
    if not manifest.is_file():
        return
    setup=json.loads(manifest.read_text())
    if company['hostname']!=setup['hostname'] or company['name']!=setup['name']:
        return
    brand=app.state.database.parent/'brand'
    with transaction(app.state.database,True) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS company_setup_applied (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        if conn.execute('SELECT 1 FROM company_setup_applied WHERE id=?',(setup['id'],)).fetchone():
            apply_icon_update(conn,brand,bundle,setup)
            return
        shop=DEFAULTS|settings(conn)
        # Retain contacts, credentials, pricing, payments and all existing records.
        data={key:shop.get(key,'') for key in FIELDS}|setup['branding']
        for key in ('brand_logo','brand_icon'):
            image=setup['images'][key]
            clean,_,_,_=sanitize((bundle/image).read_bytes(),image)
            filename=hashlib.sha256(clean).hexdigest()+'.png'
            (brand/filename).write_bytes(clean)
            (brand/filename).chmod(0o600)
            data[key]=filename
        data=validate(data)
        shop=shop|data|{'brand_custom':True}
        conn.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(shop),))
        conn.execute('UPDATE company_draft SET data=?,version=version+1,updated_at=? WHERE id=1',(json.dumps(data),now()))
        from .seed import steps_for
        for workflow in setup['workflows']:
            conn.execute('INSERT OR IGNORE INTO workflows(name,steps) VALUES(?,?)',
                         (workflow['name'],json.dumps(steps_for(workflow['production']))))
        for product in setup['products']:
            # An owner-created product always wins over the bundled starter.
            if conn.execute('SELECT 1 FROM products WHERE name=? COLLATE NOCASE',(product['name'],)).fetchone():
                continue
            cfg=validate_config(product['config'])
            workflow=conn.execute('SELECT id FROM workflows WHERE name=?',(product['workflow'],)).fetchone()
            if not workflow:
                raise ValueError('Company setup references a missing workflow')
            conn.execute('INSERT INTO products(name,category,workflow_id,config,updated_at) VALUES(?,?,?,?,?)',
                         (product['name'],product['category'],workflow['id'],json.dumps(cfg),now()))
        record_revision(conn,shop,'Platform owner',setup['note'])
        audit(conn,None,'Platform owner','company.setup_applied',{'id':setup['id']})
        conn.execute('INSERT INTO company_setup_applied VALUES(?,?)',(setup['id'],now()))
        apply_icon_update(conn,brand,bundle,setup)
