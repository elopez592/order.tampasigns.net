import json
import time
import pytest
from fastapi import HTTPException
from app.db import transaction
from app.platform import CompanyRouter
from app.subscriptions import reconcile, accessible, SubscriptionGateway
from fastapi.testclient import TestClient
from tests.test_company_platform import add_company, tenant


def removal(admin, slug, **changes):
    listed=admin.get('/api/platform/companies').json()['companies']
    company=next((c for c in listed if c['slug']==slug),None)
    return {'confirm_slug':slug,'revision':company['revision'] if company else 1,**changes}


def delete(admin, slug, **payload):
    return admin.request('DELETE','/api/platform/companies/'+slug,json=removal(admin,slug,**payload))


def test_delete_requires_platform_owner_confirmation_and_current_revision(env):
    app,admin,employee=env
    credentials=add_company(admin,'remove-me','remove.example.test')
    child=tenant(app,'remove.example.test',credentials)
    body=removal(admin,'remove-me')
    assert employee.request('DELETE','/api/platform/companies/remove-me',json=body).status_code==403
    assert child.request('DELETE','/api/platform/companies/remove-me',json=body).status_code==404
    assert delete(admin,'remove-me',confirm_slug='different').status_code==422
    assert delete(admin,'remove-me',revision=0).status_code==409
    assert admin.request('DELETE','/api/platform/companies/remove-me',json=body,headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert delete(admin,'orders-tampa').status_code==404
    assert child.get('/api/catalog').status_code==200


def test_removal_hides_workspace_retains_data_revokes_support_and_prevents_reopening(env):
    app,admin,_=env
    a=add_company(admin,'remove-me','remove.example.test')
    b=add_company(admin,'keep-me','keep.example.test')
    first=tenant(app,'remove.example.test',a);second=tenant(app,'keep.example.test',b)
    grant=admin.post('/api/platform/companies/remove-me/support',json={})
    assert grant.status_code==200
    target=app.state.database.parent/'companies'/'remove-me'/'signshop.sqlite3'
    data=target.read_bytes()
    assert delete(admin,'remove-me').status_code==200
    assert target.read_bytes()==data
    assert [c['slug'] for c in admin.get('/api/platform/companies').json()['companies']]==['keep-me']
    for path in ['/','/staff','/staff/app','/staff/billing','/api/session','/api/catalog','/brand/app-icon.png','/static/app.js']:
        assert first.get(path).status_code==404,path
    with transaction(app.state.database) as conn:
        row=dict(conn.execute("SELECT * FROM platform_companies WHERE slug='remove-me'").fetchone())
        assert row['deleted_at'] and row['status']=='closed' and not accessible(row)
        assert not conn.execute("SELECT 1 FROM platform_support_grants WHERE slug='remove-me'").fetchone()
        details=json.loads(conn.execute("SELECT details FROM events WHERE action='platform.company_deleted'").fetchone()[0])
        assert details['slug']=='remove-me' and details['records_retained']
    assert 'remove-me' not in app.state.company_apps
    assert admin.post('/api/platform/companies/remove-me/support',json={}).status_code==404
    assert admin.patch('/api/platform/companies/remove-me',json={'revision':row['revision'],'status':'active'}).status_code==404
    assert admin.post('/api/platform/companies/remove-me/billing',json={'mode':'pilot','plan_id':'business'}).status_code==404
    assert admin.put('/api/platform/companies/remove-me/connections',json={}).status_code==404
    assert delete(admin,'remove-me').json()['already_deleted']
    assert second.get('/api/catalog').status_code==200
    assert admin.get('/api/catalog').status_code==200
    assert admin.post('/api/platform/companies',json={'slug':'remove-me','name':'Replacement','owner_email':'new@example.test','hostname':'new.example.test'}).status_code==409
    assert admin.post('/api/platform/companies',json={'slug':'another','name':'Replacement','owner_email':'new@example.test','hostname':'remove.example.test'}).status_code==409
    # The archived order-payment webhook still reaches signature verification, not a login or workspace route.
    child=app.state.company_apps.get('remove-me')
    assert child is None
    first.post('/api/payments/stripe/webhook',content=b'{}',headers={'Stripe-Signature':'bad'})
    assert 'remove-me' in app.state.company_apps


class RemovalBilling:
    def __init__(self):
        self.calls=[];self.failed=False;self.customer='cus_remove';self.state='active';self.session_state='open'
    def subscription(self,identifier):
        self.calls.append(('retrieve-subscription',identifier))
        return {'id':identifier,'customer':self.customer,'status':self.state,'items':{'data':[{'price':{'id':'price_studio'},'quantity':1,'current_period_end':time.time()+86400}]}}
    def call(self,resource,method,params=None,key=None,identifier=None):
        self.calls.append((resource,method,identifier,params))
        if self.failed: raise HTTPException(502,'Fixture billing unavailable')
        if resource=='checkout.sessions':
            if method=='expire': self.session_state='expired'
            return {'id':identifier,'customer':'cus_remove','client_reference_id':'remove-me','mode':'subscription','status':self.session_state,'subscription':'sub_remove' if self.session_state=='complete' else None}
        if resource=='subscriptions' and method=='cancel':
            assert params=={'invoice_now':False,'prorate':False}
            self.state='canceled'
            return {'id':identifier,'customer':self.customer,'status':'canceled'}
        raise AssertionError((resource,method))


def billable(env, pending=True, bound=True):
    app,admin,_=env
    add_company(admin,'remove-me','remove.example.test')
    gateway=RemovalBilling();app.state.subscription_gateway=gateway
    with transaction(app.state.database,True) as conn:
        conn.execute("UPDATE platform_companies SET billing_mode='stripe',stripe_customer='cus_remove',stripe_subscription=?,plan_id='studio',subscription_status='active',paid_through=? WHERE slug='remove-me'",('sub_remove' if bound else '',time.time()+86400))
        if pending: conn.execute("INSERT INTO subscription_checkout VALUES('remove-me','studio','cs_remove','https://checkout.stripe.com/fixture',?)",(time.time()+86400,))
    return app,admin,gateway


def test_paid_removal_stops_open_checkout_and_subscription_before_hiding_company(env):
    app,admin,gateway=billable(env)
    assert delete(admin,'remove-me').status_code==409
    assert not gateway.calls
    assert delete(admin,'remove-me',cancel_billing=True).status_code==200
    assert gateway.calls[1][:3]==('checkout.sessions','expire','cs_remove')
    assert gateway.state=='canceled'
    with transaction(app.state.database) as conn:
        assert not conn.execute("SELECT 1 FROM subscription_checkout WHERE slug='remove-me'").fetchone()
    # Even a delayed authoritative active event cannot reopen an archived workspace.
    gateway.state='active'
    assert reconcile(app,gateway.subscription('sub_remove')) is False
    with transaction(app.state.database) as conn:
        row=dict(conn.execute("SELECT * FROM platform_companies WHERE slug='remove-me'").fetchone())
        assert row['subscription_status']=='canceled' and not accessible(row)


@pytest.mark.parametrize('failure',['network','foreign_customer'])
def test_failed_or_wrong_customer_billing_preserves_company(env,failure):
    app,admin,gateway=billable(env,pending=False)
    if failure=='network': gateway.failed=True
    else: gateway.customer='cus_other_company'
    response=delete(admin,'remove-me',cancel_billing=True)
    assert response.status_code in (409,502),response.text
    assert admin.get('/api/platform/companies').json()['companies'][0]['slug']=='remove-me'
    with transaction(app.state.database) as conn:
        assert conn.execute("SELECT deleted_at FROM platform_companies WHERE slug='remove-me'").fetchone()[0]==''
    if failure=='foreign_customer': assert not any(c[0]=='subscriptions' for c in gateway.calls)


def test_completed_checkout_without_webhook_is_canceled_before_removal(env):
    app,admin,gateway=billable(env,bound=False)
    gateway.session_state='complete'
    assert delete(admin,'remove-me',cancel_billing=True).status_code==200
    assert gateway.state=='canceled'
    assert any(c[:3]==('subscriptions','cancel','sub_remove') for c in gateway.calls)


def test_checkout_expiration_failure_or_wrong_owner_preserves_workspace(env,monkeypatch):
    app,admin,gateway=billable(env,bound=False)
    original=gateway.call
    def wrong_checkout(resource,method,params=None,key=None,identifier=None):
        result=original(resource,method,params,key,identifier)
        if resource=='checkout.sessions' and method=='retrieve': result['customer']='cus_unrelated'
        return result
    monkeypatch.setattr(gateway,'call',wrong_checkout)
    assert delete(admin,'remove-me',cancel_billing=True).status_code==409
    assert not any(c[1]=='expire' for c in gateway.calls)
    monkeypatch.setattr(gateway,'call',original)
    gateway.failed=True
    assert delete(admin,'remove-me',cancel_billing=True).status_code==502
    assert admin.get('/api/platform/companies').json()['companies'][0]['slug']=='remove-me'


def test_unconfirmed_cancellation_response_preserves_workspace(env,monkeypatch):
    app,admin,gateway=billable(env,pending=False)
    original=gateway.call
    def unconfirmed(resource,method,params=None,key=None,identifier=None):
        result=original(resource,method,params,key,identifier)
        result['status']='active'
        return result
    monkeypatch.setattr(gateway,'call',unconfirmed)
    assert delete(admin,'remove-me',cancel_billing=True).status_code==502
    assert admin.get('/api/platform/companies').json()['companies'][0]['slug']=='remove-me'
