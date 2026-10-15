"""Sticker bundles can be paid before design/proofs, never printed without approval."""
import json
import uuid
import pytest
from app import job_terms
from app.db import transaction
from app.domain import gate_reason,get_job
from tests.conftest import anonymous
from tests.test_checkout_privacy import live_setup,open_session,paid_object,send_event


def pack_items(client,design=False,packs=50):
    product=next(p for p in client.get('/api/catalog').json()['products'] if p['name']=='Sticker packs')
    return [{'product_id':product['id'],'quantity':packs,'proof_after_payment':False,'sticker_pack':{
        'stickers':[{'name':'Van','width':3.5,'height':3,'copies':2,'design_requested':design},
                    {'name':'Logo','width':2,'height':2,'copies':1}],
        'notes':'Create a blue company van sticker.'}}]


@pytest.mark.parametrize('design',[False,True])
def test_pay_before_proof_without_uploading_artwork(live_setup,design):
    app,admin,_=live_setup
    client=anonymous(app)
    items=pack_items(client,design)
    quote=client.post('/api/calculate',json={'items':items}).json()
    assert quote['review_required'] is False
    line=quote['lines'][0]
    assert line['quote_only'] is False
    assert line['proof_after_payment'] is True
    assert line['design_requested'] is design
    assert line['sticker_pack_pricing']['design_fee_cents']==(2500 if design else 0)
    response=client.post('/api/orders',json={'items':items,'fingerprint':quote['fingerprint'],
        'request_id':str(uuid.uuid4()),'customer_name':'Bundle checkout test','customer_email':'bundle@example.test',
        'title':'Sticker bundle','fulfillment':'pickup','confirm':True,'terms_version':job_terms.VERSION})
    assert response.status_code==200,response.text
    order=response.json();client.headers['X-CSRF-Token']=order['csrf']
    session=open_session(app,client,order['job_id'])
    body=json.loads(session['request_body'])
    assert 'after payment' in body['custom_text[submit][message]']
    assert session['merchandise_cents']==quote['subtotal_cents']
    # A filename/reference upload cannot bypass a complete pack proof.
    approval=client.post('/api/portal/artwork-preview/approve',json={
        'name':'Bundle checkout test','confirm':True,'terms_version':job_terms.VERSION,
        'quote_version':1,'files':[{'asset_id':1,'sha256':'not-an-approved-proof','line_indices':[0]}]})
    assert approval.status_code==409,approval.text
    result=send_event(app,paid_object(app,session))
    assert result.status_code==200,result.text
    with transaction(app.state.database,True) as conn:
        job=get_job(conn,order['job_id'])
        assert conn.execute('SELECT COUNT(*) FROM proofs WHERE job_id=?',(job['id'],)).fetchone()[0]==0
        task=conn.execute("SELECT * FROM tasks WHERE job_id=? AND gate='production' ORDER BY id LIMIT 1",(job['id'],)).fetchone()
        conn.execute("UPDATE tasks SET status='done' WHERE job_id=? AND id!=?",(job['id'],task['id']))
        assert 'proof package must be approved' in gate_reason(conn,job,task)


@pytest.mark.parametrize('packs',[50,1000])
def test_design_fee_is_once_per_design_not_per_copy_or_pack(live_setup,packs):
    app,_,_=live_setup
    client=anonymous(app)
    without=client.post('/api/calculate',json={'items':pack_items(client,False,packs)}).json()
    with_design=client.post('/api/calculate',json={'items':pack_items(client,True,packs)}).json()
    assert with_design['subtotal_cents']-without['subtotal_cents']==2500
    assert with_design['lines'][0]['sticker_pack_pricing']['design_count']==1


def test_design_choice_must_be_a_boolean(env):
    app,_,_=env;client=anonymous(app)
    items=pack_items(client)
    items[0]['sticker_pack']['stickers'][0]['design_requested']='false'
    assert client.post('/api/calculate',json={'items':items}).status_code==422
