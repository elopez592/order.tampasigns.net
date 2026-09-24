"""First-party, opt-in traffic measurement and owner-only conversion reports.

Browser actions are untrusted observations, never purchases. Submitted requests
come from jobs; collected amounts come only from existing verified payment rows.
No form contents, raw IPs, artwork names or private portal URLs are stored here.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import logging
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from .db import transaction, now
from .security import digest, rate_limit

INDEXNOW_KEY = '70ad53bec9894a16b7e14c8d802eca39'
MAIN_ORIGIN = 'https://www.tampasigns.net'
ORDER_ORIGIN = 'https://orders.tampasigns.net'
EVENTS = {'page_view', 'product_view', 'start_project', 'add_to_cart', 'begin_checkout', 'upload_file', 'canva_click', 'design_help_click', 'phone_click', 'email_click'}
MAIN_PATHS = {'/', '/contact.html', '/blog/', '/privacy.html',
    '/blog/vehicle-wraps-lettering-fleet-graphics.html', '/blog/die-cut-stickers-labels-decals.html',
    '/blog/acm-signs-rigid-panels.html', '/blog/window-graphics-door-decals-frosted-vinyl.html',
    '/blog/banners-event-signs-grand-opening.html', '/blog/custom-shirts-hats-dtf-embroidery.html',
    '/blog/sign-installation-removal-vinyl-adhesive.html', '/blog/business-cards-flyers-print-marketing.html',
    '/service-areas/tampa-bay-sign-shop-service-area.html', '/service-areas/st-pete-clearwater-brandon-lutz-signs-wraps.html'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS marketing_sessions (
 sid TEXT PRIMARY KEY, created_at TEXT NOT NULL, last_seen REAL NOT NULL,
 entry_site TEXT NOT NULL, landing_path TEXT NOT NULL, source TEXT NOT NULL,
 medium TEXT NOT NULL, campaign TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS marketing_events (
 event_id TEXT PRIMARY KEY, sid TEXT NOT NULL, created_at TEXT NOT NULL,
 site TEXT NOT NULL, path TEXT NOT NULL, event TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS marketing_events_date ON marketing_events(created_at);
CREATE INDEX IF NOT EXISTS marketing_events_session ON marketing_events(sid);
CREATE TABLE IF NOT EXISTS marketing_conversions (
 job_id INTEGER PRIMARY KEY REFERENCES jobs(id), created_at TEXT NOT NULL,
 sid TEXT, entry_site TEXT NOT NULL, landing_path TEXT NOT NULL,
 source TEXT NOT NULL, medium TEXT NOT NULL, campaign TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS marketing_conversion_date ON marketing_conversions(created_at);
CREATE TABLE IF NOT EXISTS marketing_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS marketing_submissions (
 host TEXT PRIMARY KEY, submitted_at TEXT NOT NULL, status INTEGER NOT NULL,
 url_count INTEGER NOT NULL, detail TEXT NOT NULL
);
'''


def safe_label(value, fallback=''):
    if not isinstance(value, str) or len(value) > 80:
        return fallback
    value = value.lower().strip()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,79}', value) or re.search(r'\d{7}', value):
        return fallback
    return value


def token_hash(value):
    return digest(value) if isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value) else None


def capture_conversion(conn, request, job_id):
    """Fail-open savepoint: optional analytics must never break an order."""
    try:
        conn.execute('SAVEPOINT marketing_capture')
        sid = token_hash(request.cookies.get('ts_measure_sid'))
        opted_in = request.cookies.get('ts_measure_choice') == 'yes'
        excluded = request.cookies.get('ts_measure_exclude') == 'yes'
        session = conn.execute('SELECT * FROM marketing_sessions WHERE sid=? AND last_seen>?',
                               (sid, time.time() - 1800)).fetchone() if sid and opted_in and not excluded else None
        if session:
            conn.execute('INSERT OR IGNORE INTO marketing_conversions VALUES (?,?,?,?,?,?,?,?,?)',
                         (job_id, now(), sid, session['entry_site'], session['landing_path'],
                          session['source'], session['medium'], session['campaign'],))
        else:
            conn.execute('INSERT OR IGNORE INTO marketing_conversions VALUES (?,?,?,?,?,?,?,?)',
                         (job_id, now(), None, 'unattributed', '', 'unattributed', '', ''))
        conn.execute('RELEASE marketing_capture')
    except Exception:
        conn.execute('ROLLBACK TO marketing_capture')
        conn.execute('RELEASE marketing_capture')
        logging.getLogger(__name__).warning('Optional conversion attribution was not saved.')


def report(conn, start=None, end=None, site='all'):
    eastern = ZoneInfo('America/New_York')
    today = datetime.now(eastern).date()
    try:
        end_date = date.fromisoformat(end) if end else today
        start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)
    except (ValueError, TypeError):
        raise HTTPException(400, 'Use YYYY-MM-DD dates.')
    if start_date > end_date or (end_date-start_date).days > 365:
        raise HTTPException(400, 'Select a date range of up to 366 days.')
    if site not in {'all','main','orders','unattributed'}:
        raise HTTPException(400, 'Invalid site filter.')
    lo = datetime.combine(start_date, datetime.min.time(), eastern).astimezone(timezone.utc).isoformat(timespec='seconds')
    hi = datetime.combine(end_date+timedelta(days=1), datetime.min.time(), eastern).astimezone(timezone.utc).isoformat(timespec='seconds')
    rows = conn.execute('''SELECT j.id, j.number, j.created_at, j.source AS request_type,
      COALESCE(c.entry_site,'unattributed') AS entry_site, COALESCE(c.source,'unattributed') AS source,
      COALESCE(c.medium,'') AS medium, COALESCE(c.campaign,'') AS campaign,
      COALESCE(c.landing_path,'') AS landing_path, c.sid,
      COALESCE((SELECT SUM(p.amount_cents) FROM payments p WHERE p.job_id=j.id AND p.voided_at IS NULL),0)
      + COALESCE((SELECT SUM(MAX(0,p.amount_cents-p.refunded_cents)) FROM online_payments p
        WHERE p.job_id=j.id AND p.disputed=0),0) AS collected_cents
      FROM jobs j LEFT JOIN marketing_conversions c ON c.job_id=j.id
      WHERE j.created_at>=? AND j.created_at<? AND j.source IN ('customer','custom','checkout')
      ORDER BY j.created_at DESC''',(lo,hi)).fetchall()
    leads = [dict(row) for row in rows if site=='all' or row['entry_site']==site]
    sessions = [dict(row) for row in conn.execute('SELECT * FROM marketing_sessions WHERE created_at>=? AND created_at<?',(lo,hi))
                if site=='all' or row['entry_site']==site]
    session_ids = {row['sid'] for row in sessions}
    events = [dict(row) for row in conn.execute('SELECT event,site,path,COUNT(*) AS count FROM marketing_events WHERE created_at>=? AND created_at<? GROUP BY event,site,path',(lo,hi))
              if site=='all' or row['site']==site]
    totals = {event:sum(row['count'] for row in events if row['event']==event) for event in EVENTS}
    converted = {row['sid'] for row in leads if row['sid'] in session_ids}
    totals.update(sessions=len(sessions), submitted_requests=len(leads),
      quote_requests=sum(row['request_type']!='checkout' for row in leads),
      checkout_orders=sum(row['request_type']=='checkout' for row in leads),
      paid_jobs=sum(row['collected_cents']>0 for row in leads),
      collected_cents=sum(row['collected_cents'] for row in leads),
      attributed_requests=sum(bool(row['sid']) for row in leads),
      converted_sessions=len(converted), conversion_rate=round(100*len(converted)/len(sessions),2) if sessions else None)
    groups = {}
    for s in sessions:
        key = (s['source'],s['medium'],s['campaign'])
        g=groups.setdefault(key,{'source':key[0],'medium':key[1],'campaign':key[2],'sessions':0,'requests':0,'collected_cents':0})
        g['sessions']+=1
    for row in leads:
        key=(row['source'],row['medium'],row['campaign'])
        g=groups.setdefault(key,{'source':key[0],'medium':key[1],'campaign':key[2],'sessions':0,'requests':0,'collected_cents':0})
        g['requests']+=1;g['collected_cents']+=row['collected_cents']
    pages=sorted([row for row in events if row['event']=='page_view'],key=lambda row:row['count'],reverse=True)[:25]
    for row in leads:row.pop('sid',None)
    first=conn.execute("SELECT value FROM marketing_meta WHERE key='installed_at'").fetchone()
    return {'period':{'start':str(start_date),'end':str(end_date),'timezone':'America/New_York','site':site},
      'tracking_since':first['value'] if first else None,'totals':totals,'channels':sorted(groups.values(),key=lambda row:row['requests'],reverse=True),
      'pages':pages,'requests':leads[:200],'request_count':len(leads),
      'submissions':[dict(row) for row in conn.execute('SELECT * FROM marketing_submissions')],
      'definitions':{'traffic':'Opt-in browser observations; not unique people. 30-minute sessions shared across the main and ordering subdomains. Staff browsers, DNT and GPC are excluded.',
      'conversion':'Share of measured sessions first seen in the selected period with a server-confirmed request submitted in that period. No attribution is invented for people who decline measurement.',
      'collected':'Current net verified receipts for requests CREATED in the selected period, including deposits, tax and shipping; voided payments, refunds and active disputes are excluded. This is not booked revenue or profit.',
      'history':'Traffic starts at installation, not retroactively. Older public requests appear as unattributed. Traffic retained 90 days; request attribution retained 365 days.'}}


def install(app, database, public_url, production, require_admin):
    with sqlite3.connect(database) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO marketing_meta VALUES ('installed_at',?)",(now(),))
    origins={MAIN_ORIGIN:'main',ORDER_ORIGIN:'orders'}
    if not production:
        origins.update({public_url:'orders','http://localhost:8000':'orders','http://localhost:3000':'main','http://testserver':'orders'})

    def headers(origin):
        return {'Access-Control-Allow-Origin':origin,'Vary':'Origin','Cache-Control':'no-store',
                'Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type'}

    @app.options('/api/marketing/event')
    def preflight(request: Request):
        origin=request.headers.get('origin','')
        if origin not in origins:raise HTTPException(403,'Origin not allowed.')
        return Response(status_code=204,headers=headers(origin))

    @app.post('/api/marketing/event')
    async def collect(request: Request):
        origin=request.headers.get('origin','')
        if origin not in origins:raise HTTPException(403,'Origin not allowed.')
        if request.headers.get('dnt')=='1' or request.headers.get('sec-gpc')=='1' or getattr(request.state,'user',None):
            return Response(status_code=204,headers=headers(origin))
        try:length=int(request.headers.get('content-length','0'))
        except ValueError:raise HTTPException(400,'Invalid length.')
        if length>4096:raise HTTPException(413,'Event too large.')
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>4096:raise HTTPException(413,'Event too large.')
        try:data=json.loads(body)
        except (ValueError,UnicodeDecodeError):raise HTTPException(400,'Invalid event.')
        allowed={'sid','event_id','event','path','consent','source','medium','campaign'}
        if not isinstance(data,dict) or set(data)-allowed or data.get('consent') is not True:
            raise HTTPException(400,'Unexpected event fields or missing consent.')
        sid=token_hash(data.get('sid'));event_id=token_hash(data.get('event_id'))
        event=data.get('event');path=data.get('path');site=origins[origin]
        if not sid or not event_id or event not in EVENTS or not isinstance(path,str):
            raise HTTPException(400,'Invalid event.')
        with transaction(database,write=True) as conn:
            paths=MAIN_PATHS if site=='main' else {'/','/products','/project'}|{'/products/'+re.sub(r'[^a-z0-9]+','-', ('vehicle wraps' if row['name'].lower()=='partial vehicle wraps' else row['name'].lower()).replace('&',' and ')).strip('-') for row in conn.execute('SELECT name FROM products WHERE active=1 AND public=1')}
            if path not in paths:raise HTTPException(400,'Only public pages can be measured.')
            ip=request.client.host if request.client else 'unknown'
            if not rate_limit(conn,'marketing:'+digest(ip),180,60):raise HTTPException(429,'Please try later.')
            if conn.execute('SELECT 1 FROM marketing_events WHERE event_id=?',(event_id,)).fetchone():
                return Response(status_code=204,headers=headers(origin))
            existing=conn.execute('SELECT last_seen FROM marketing_sessions WHERE sid=?',(sid,)).fetchone()
            if existing and existing['last_seen']<time.time()-1800:
                raise HTTPException(409,'Measurement session expired.')
            stamp=now()
            conn.execute('INSERT OR IGNORE INTO marketing_sessions VALUES (?,?,?,?,?,?,?,?)',
              (sid,stamp,time.time(),site,path,safe_label(data.get('source'),'direct'),safe_label(data.get('medium')),safe_label(data.get('campaign'))))
            conn.execute('UPDATE marketing_sessions SET last_seen=? WHERE sid=?',(time.time(),sid))
            conn.execute('INSERT INTO marketing_events VALUES (?,?,?,?,?,?)',(event_id,sid,stamp,site,path,event))
            cleanup=conn.execute("SELECT value FROM marketing_meta WHERE key='cleanup'").fetchone()
            if not cleanup or float(cleanup['value'])<time.time()-3600:
                cutoff=(datetime.now(timezone.utc)-timedelta(days=90)).isoformat(timespec='seconds')
                conn.execute('DELETE FROM marketing_events WHERE created_at<?',(cutoff,))
                conn.execute('DELETE FROM marketing_sessions WHERE last_seen<?',(time.time()-90*86400,))
                conn.execute('DELETE FROM marketing_conversions WHERE created_at<?',((datetime.now(timezone.utc)-timedelta(days=365)).isoformat(timespec='seconds'),))
                conn.execute("INSERT OR REPLACE INTO marketing_meta VALUES ('cleanup',?)",(str(time.time()),))
        return Response(status_code=204,headers=headers(origin))

    @app.get('/'+INDEXNOW_KEY+'.txt')
    def indexnow_key():
        return Response(INDEXNOW_KEY,media_type='text/plain',headers={'Cache-Control':'public, max-age=3600'})

    @app.get('/api/admin/marketing')
    def dashboard(request: Request, start: str|None=None, end: str|None=None, site: str='all', user=Depends(require_admin)):
        with transaction(database) as conn:return report(conn,start,end,site)

    @app.get('/api/admin/marketing.csv')
    def export(request: Request, start: str|None=None, end: str|None=None, site: str='all', user=Depends(require_admin)):
        with transaction(database) as conn:data=report(conn,start,end,site)
        stream=io.StringIO();writer=csv.writer(stream)
        writer.writerow(['Source','Medium','Campaign','Measured sessions','Submitted requests','Net receipts USD'])
        def cell(v):
            s=str(v);return "'"+s if s[:1] in ('=','+','-','@','\t','\r') else s
        for r in data['channels']:writer.writerow([cell(r['source']),cell(r['medium']),cell(r['campaign']),r['sessions'],r['requests'],f"{r['collected_cents']/100:.2f}"])
        return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="tampa-marketing.csv"'})

    @app.post('/api/admin/marketing/indexnow')
    def submit_indexnow(request: Request,user=Depends(require_admin)):
        with transaction(database,write=True) as conn:
            if not rate_limit(conn,'indexnow:'+str(user['id']),1,3600):raise HTTPException(429,'Submission is limited to once per hour.')
        results=[]
        for origin in (MAIN_ORIGIN,ORDER_ORIGIN):
            host=urlsplit(origin).hostname
            try:
                with httpx.Client(timeout=30,follow_redirects=False) as client:
                    key=client.get(origin+'/'+INDEXNOW_KEY+'.txt');key.raise_for_status()
                    if key.text.strip()!=INDEXNOW_KEY:raise ValueError('Key file not verified')
                    response=client.get(origin+'/sitemap.xml');response.raise_for_status()
                    if len(response.content)>2_000_000:raise ValueError('Sitemap too large')
                    urls=[n.text for n in ET.fromstring(response.content).findall('{*}url/{*}loc')]
                    if not urls or len(urls)>10000 or any(urlsplit(u).scheme!='https' or urlsplit(u).netloc!=host for u in urls):raise ValueError('Sitemap scope check failed')
                    answer=client.post('https://www.bing.com/indexnow',json={'host':host,'key':INDEXNOW_KEY,'keyLocation':origin+'/'+INDEXNOW_KEY+'.txt','urlList':urls})
                    status=answer.status_code
                    detail='URLs received; indexing is not guaranteed.' if status==200 else 'Received; key validation pending.' if status==202 else 'Submission not accepted; retry after reviewing the response status.'
                row={'host':host,'submitted_at':now(),'status':status,'url_count':len(urls),'detail':detail}
            except Exception:
                row={'host':host,'submitted_at':now(),'status':0,'url_count':0,'detail':'Could not verify or submit this site. No indexing success is claimed.'}
            with transaction(database,write=True) as conn:
                conn.execute('INSERT OR REPLACE INTO marketing_submissions VALUES (?,?,?,?,?)',tuple(row.values()))
            results.append(row)
        return {'results':results}
