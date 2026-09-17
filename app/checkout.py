"""Hosted card checkout. No card data enters this application.

All prices are calculated on the server and frozen on an order. Signed Stripe
webhooks, not redirect parameters, record receipts. Gateway calls are deliberately
outside SQLite write transactions. Keys come only from the server environment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import uuid
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from .db import audit, now, settings, transaction
from .pricing import calculate, public_quote, cents, cent_round
from .security import digest

API_VERSION = '2026-02-25.clover'


class StripeGateway:
    def __init__(self):
        self.key = os.getenv('STRIPE_SECRET_KEY', '')
        self.webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET', '')
        self.live = self.key.startswith('sk_live_')
        self.ready = bool(self.key.startswith(('sk_test_', 'sk_live_')) and self.webhook_secret.startswith('whsec_'))

    def request(self, path, data=None, idempotency_key=None):
        if not self.ready:
            raise HTTPException(503, 'Online payments are not connected. Please contact the shop.')
        headers = {'Authorization': 'Bearer ' + self.key, 'Stripe-Version': API_VERSION}
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        try:
            with httpx.Client(timeout=25, follow_redirects=False, trust_env=False) as client:
                response = client.request('POST' if data is not None else 'GET',
                                          'https://api.stripe.com/v1/' + path,
                                          data=data, headers=headers)
            if not response.is_success:
                raise HTTPException(502, 'The payment provider could not open checkout. Your order is saved; please retry or contact the shop.')
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError('Invalid gateway response')
            return result
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, 'Unable to reach the payment provider. Your order is saved; retry shortly.')

    def create_session(self, data, key):
        return self.request('checkout/sessions', data, key)

    def retrieve_session(self, session_id):
        if not re.fullmatch(r'cs_[A-Za-z0-9_]+', session_id):
            raise HTTPException(422, 'Invalid payment session.')
        return self.request('checkout/sessions/' + session_id)

    def tax_rate(self, percentage):
        key = 'tampa-tax-' + digest(str(percentage))[:32]
        result = self.request('tax_rates', {'display_name': 'Sales tax', 'inclusive': 'false',
                              'percentage': str(percentage)}, key)
        tax_id = result.get('id', '')
        if not re.fullmatch(r'txr_[A-Za-z0-9]+', tax_id):
            raise HTTPException(502, 'The payment provider returned an invalid tax rate.')
        return tax_id

    def verify_event(self, raw, signature):
        if not self.ready:
            raise HTTPException(503, 'Payment webhook is not configured.')
        parts = {}
        for pair in signature.split(','):
            key, sep, value = pair.partition('=')
            if sep:
                parts.setdefault(key.strip(), []).append(value.strip())
        try:
            timestamp = int(parts['t'][0])
        except (KeyError, IndexError, ValueError):
            raise HTTPException(400, 'Invalid webhook signature.')
        if abs(time.time() - timestamp) > 300:
            raise HTTPException(400, 'Expired webhook signature.')
        expected = hmac.new(self.webhook_secret.encode(), str(timestamp).encode()+b'.'+raw, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in parts.get('v1', [])):
            raise HTTPException(400, 'Invalid webhook signature.')
        try:
            event = json.loads(raw)
            if not isinstance(event, dict) or not isinstance(event.get('data', {}).get('object'), dict):
                raise ValueError()
            if not isinstance(event.get('id'), str) or not event['id'].startswith('evt_'):
                raise ValueError()
            if event.get('livemode') is not self.live:
                raise HTTPException(400, 'Webhook payment mode does not match the configured account.')
            return event
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, 'Invalid webhook event.')


def availability(shop, gateway):
    common = bool(shop.get('checkout_enabled') and shop.get('rates_live')
                  and shop.get('checkout_tax_reviewed') and gateway.ready)
    pickup = bool(common and shop.get('checkout_pickup_enabled') and shop.get('checkout_pickup_address', '').strip())
    shipping = bool(common and shop.get('checkout_shipping_enabled'))
    return {'available': pickup or shipping, 'pickup': pickup, 'shipping': shipping,
            'pickup_address': shop.get('checkout_pickup_address', ''),
            'shipping_cents': cents(shop.get('checkout_shipping_price', '0')),
            'pickup_tax_percent': shop.get('checkout_pickup_tax_percent', '0'),
            'terms': shop.get('checkout_terms', ''), 'test_mode': gateway.ready and not gateway.live,
            'provider': 'stripe' if gateway.ready else None}


def checkout_policy(shop, fulfillment):
    # Immutable policy snapshot: editing settings never changes a submitted order.
    return {'fulfillment': fulfillment, 'pickup_address': shop['checkout_pickup_address'],
            'tax_percent': shop['checkout_pickup_tax_percent'],
            'shipping_cents': cents(shop['checkout_shipping_price']) if fulfillment == 'shipping' else 0,
            'terms': shop['checkout_terms'], 'tax_mode': 'automatic' if fulfillment == 'shipping' else 'pickup_fixed'}


def eligible_quote(conn, items):
    if not isinstance(items, list) or len(items) != 1:
        raise HTTPException(422, 'Checkout currently supports one product/design per order. Request a quote for combined projects.')
    quote = calculate(conn, items)
    if not 50 <= quote['subtotal_cents'] <= 99_999_999:
        raise HTTPException(422, 'This amount requires a custom quote rather than online checkout.')
    if quote['review_required']:
        raise HTTPException(422, 'Wraps, installation and custom sizes require a reviewed quote, not instant checkout.')
    return quote


def order_for_job(conn, job_id):
    return conn.execute('SELECT * FROM checkout_orders WHERE job_id=?', (job_id,)).fetchone()


def order_summary(conn, job, gateway):
    order = order_for_job(conn, job['id'])
    if not order:
        return None
    policy = json.loads(order['policy'])
    receipt = conn.execute('SELECT * FROM online_payments WHERE job_id=?', (job['id'],)).fetchone()
    latest = conn.execute('SELECT status FROM checkout_sessions WHERE order_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1', (order['id'],)).fetchone()
    if receipt:
        status = 'refunded' if receipt['refunded_cents'] >= receipt['amount_cents'] else 'partly_refunded' if receipt['refunded_cents'] else 'paid'
        if receipt['disputed']:
            status = 'payment_review'
    else:
        status = 'payment_review' if latest and latest['status'] == 'review' else 'awaiting_payment'
    return {'status': status, 'fulfillment': order['fulfillment'],
            'pickup_address': policy['pickup_address'] if order['fulfillment']=='pickup' else '',
            'can_pay': not receipt and not job['archived'] and status != 'payment_review' and availability(settings(conn), gateway)['available'],
            'tax_pending': order['fulfillment']=='shipping' and not receipt,
            'test_mode': not gateway.live}


def start_checkout(database, job_id, gateway, public_url):
    """Create/reuse exactly one active session. Retried creates share an idempotency key."""
    with transaction(database, True) as conn:
        from .domain import get_job
        job = get_job(conn, job_id)
        order = order_for_job(conn, job_id)
        if not order or job['archived']:
            raise HTTPException(409, 'This order is not available for online checkout.')
        if conn.execute('SELECT id FROM online_payments WHERE job_id=?', (job_id,)).fetchone():
            raise HTTPException(409, 'A payment was already received. Contact the shop about adjustments; do not pay again.')
        available = availability(settings(conn), gateway)
        if not available.get(order['fulfillment']):
            raise HTTPException(503, 'Online checkout is currently unavailable for this delivery method. Your order is saved.')
        previous = conn.execute("SELECT * FROM checkout_sessions WHERE order_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (order['id'],)).fetchone()
        if previous and previous['status']=='review':
            raise HTTPException(409, 'Payment needs shop review before trying again.')
        quote = json.loads(job['quote_snapshot'])
        policy = json.loads(order['policy'])
        # Never mark an old session expired from our clock alone: reconcile with Stripe first.
        current = dict(previous) if previous and previous['status'] in ('creating','open','paid') else None
        job_data, order_data = dict(job), dict(order)
        if current is None:
            session_key = uuid.uuid4().hex
            expires_at = int(time.time()) + 3600
            conn.execute('''INSERT INTO checkout_sessions(id,order_id,quote_version,merchandise_cents,shipping_cents,expires_at,created_at)
                VALUES(?,?,?,?,?,?,?)''', (session_key, order['id'], job['quote_version'], quote['subtotal_cents'], policy['shipping_cents'], expires_at, now()))
            current = dict(conn.execute('SELECT * FROM checkout_sessions WHERE id=?', (session_key,)).fetchone())
    if current['stripe_id']:
        live = gateway.retrieve_session(current['stripe_id'])
        if live.get('payment_status') == 'paid':
            # Fetch is authoritative too; webhook eventually deduplicates by session/intent.
            with transaction(database, True) as conn:
                ok = reconcile_paid(conn, current, live, 'reconcile:'+current['stripe_id'], gateway.live)
            if not ok:
                raise HTTPException(409, 'Payment requires shop review. Please do not pay again.')
            return {'paid': True, 'url': public_url + '/portal?payment=received'}
        if live.get('status') == 'expired' and current['status']=='open':
            with transaction(database, True) as conn:
                conn.execute("UPDATE checkout_sessions SET status='expired' WHERE id=? AND status='open'", (current['id'],))
            return start_checkout(database, job_id, gateway, public_url)
        if live.get('status') == 'complete':
            raise HTTPException(409, 'The payment provider is confirming this payment. Please refresh shortly; do not pay again.')
        if current['url']:
            return {'url': current['url']}
    if current['expires_at'] < time.time()+1800 and not current['stripe_id']:
        # An interrupted unknown create may exist at Stripe. Preserve its idempotency key,
        # never create a second payment session silently. Operator reconciliation is required.
        raise HTTPException(409, 'This interrupted checkout needs shop review before restarting payment.')
    if current['request_body']:
        body = json.loads(current['request_body'])
    else:
        line = quote['lines'][0]
        body = {'mode':'payment', 'payment_method_types[0]':'card',
                'success_url': public_url + '/portal?payment=received',
                'cancel_url': public_url + '/portal?payment=cancelled',
                'client_reference_id': order_data['id'], 'customer_email': job_data['customer_email'],
                'metadata[job_id]': str(job_id), 'metadata[checkout_id]': current['id'],
                'metadata[quote_version]': str(job_data['quote_version']),
                'payment_intent_data[metadata][job_id]': str(job_id),
                'line_items[0][price_data][currency]':'usd',
                'line_items[0][price_data][unit_amount]':str(current['merchandise_cents']),
                'line_items[0][price_data][product_data][name]':line['name'],
                'line_items[0][price_data][product_data][description]':f"{line['quantity']} items, {line['width']} x {line['height']} inches. {job_data['number']}",
                'line_items[0][price_data][tax_behavior]':'exclusive',
                'line_items[0][quantity]':'1', 'billing_address_collection':'required',
                'expires_at':str(int(current['expires_at'])),
                'custom_text[submit][message]':'Your proof approval is required before production.'}
        if order_data['fulfillment'] == 'shipping':
            body.update({'automatic_tax[enabled]':'true', 'shipping_address_collection[allowed_countries][0]':'US',
                         'shipping_options[0][shipping_rate_data][type]':'fixed_amount',
                         'shipping_options[0][shipping_rate_data][display_name]':'Standard shipping',
                         'shipping_options[0][shipping_rate_data][fixed_amount][amount]':str(policy['shipping_cents']),
                         'shipping_options[0][shipping_rate_data][fixed_amount][currency]':'usd',
                         'shipping_options[0][shipping_rate_data][tax_behavior]':'exclusive'})
        elif Decimal(policy['tax_percent']) > 0:
            body['line_items[0][tax_rates][0]'] = gateway.tax_rate(policy['tax_percent'])
        with transaction(database, True) as conn:
            # First writer wins, keeping simultaneous retries byte-for-byte identical.
            conn.execute('UPDATE checkout_sessions SET request_body=? WHERE id=? AND request_body IS NULL', (json.dumps(body),current['id']))
            body = json.loads(conn.execute('SELECT request_body FROM checkout_sessions WHERE id=?',(current['id'],)).fetchone()[0])
    result = gateway.create_session(body, 'tampa-checkout-'+current['id'])
    sid, url = result.get('id',''), result.get('url','')
    if not re.fullmatch(r'cs_[A-Za-z0-9_]+', sid) or urlsplit(url).scheme!='https' or urlsplit(url).hostname!='checkout.stripe.com':
        raise HTTPException(502, 'Payment provider returned an invalid checkout link.')
    with transaction(database, True) as conn:
        conn.execute("UPDATE checkout_sessions SET stripe_id=?,url=?,status=CASE WHEN status='creating' THEN 'open' ELSE status END WHERE id=?", (sid,url,current['id']))
    return {'url':url}


def reconcile_paid(conn, session, data, event_id, live):
    from .domain import get_job
    order = conn.execute('SELECT * FROM checkout_orders WHERE id=?',(session['order_id'],)).fetchone()
    job = get_job(conn, order['job_id'])
    policy = json.loads(order['policy'])
    breakdown = data.get('total_details') or {}
    tax, shipping = breakdown.get('amount_tax', 0), breakdown.get('amount_shipping', 0)
    total = data.get('amount_total')
    intent = data.get('payment_intent')
    metadata = data.get('metadata') or {}
    correct = (data.get('payment_status') == 'paid' and data.get('currency') == 'usd'
        and data.get('livemode') is live and data.get('mode') == 'payment'
        and data.get('client_reference_id') == order['id']
        and metadata.get('checkout_id') == session['id'] and metadata.get('job_id') == str(job['id'])
        and metadata.get('quote_version') == str(session['quote_version'])
        and session['quote_version'] == job['quote_version'] and not job['archived']
        and (not session['stripe_id'] or session['stripe_id'] == data.get('id'))
        and isinstance(intent,str) and intent.startswith('pi_')
        and type(tax) is int and tax >= 0 and type(shipping) is int
        and shipping == session['shipping_cents'] and breakdown.get('amount_discount',0)==0
        and data.get('amount_subtotal') == session['merchandise_cents']
        and type(total) is int and total == session['merchandise_cents']+shipping+tax)
    if order['fulfillment']=='pickup':
        correct = correct and tax == cent_round(Decimal(session['merchandise_cents'])*Decimal(policy['tax_percent'])/100)
    else:
        correct = correct and (data.get('automatic_tax') or {}).get('status') == 'complete'
    if not correct:
        conn.execute("UPDATE checkout_sessions SET status='review' WHERE id=?",(session['id'],))
        audit(conn,job['id'],'Payment provider','checkout.needs_review',{'event_id':event_id,'session_id':data.get('id')},False)
        return False
    existing = conn.execute('SELECT id FROM online_payments WHERE session_id=? OR payment_intent=?',(data['id'],intent)).fetchone()
    if not existing:
        adjustment = conn.execute('SELECT * FROM payment_adjustments WHERE payment_intent=?',(intent,)).fetchone()
        conn.execute('''INSERT INTO online_payments(job_id,session_id,payment_intent,amount_cents,refunded_cents,disputed,event_id,created_at)
            VALUES(?,?,?,?,?,?,?,?)''',(job['id'],data['id'],intent,total,
            min(total,adjustment['refunded_cents']) if adjustment else 0, adjustment['disputed'] if adjustment else 0,event_id,now()))
        conn.execute('UPDATE jobs SET tax_cents=?,shipping_cents=?,charges_verified=1 WHERE id=?',(tax,shipping,job['id']))
        audit(conn,job['id'],'Payment provider','payment.received',{'amount_cents':total},True)
        # Shipping details belong to staff fulfillment, never to the global public catalog.
        address = (data.get('collected_information') or {}).get('shipping_details') or data.get('shipping_details')
        if address:
            audit(conn,job['id'],'Payment provider','checkout.shipping_address',address,False)
    conn.execute("UPDATE checkout_sessions SET status='paid',stripe_id=? WHERE id=?",(data['id'],session['id']))
    return True


def process_event(conn, event, gateway):
    if conn.execute('SELECT id FROM webhook_events WHERE id=?',(event['id'],)).fetchone():
        return {'received':True,'duplicate':True}
    kind, data = event.get('type',''), event['data']['object']
    if kind in ('checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.expired'):
        key = (data.get('metadata') or {}).get('checkout_id','')
        session = conn.execute('SELECT * FROM checkout_sessions WHERE id=?',(key,)).fetchone()
        if session:
            if kind=='checkout.session.expired':
                if session['stripe_id']==data.get('id'):
                    conn.execute("UPDATE checkout_sessions SET status='expired' WHERE id=? AND status IN ('creating','open')",(key,))
            elif data.get('payment_status')=='paid':
                reconcile_paid(conn,session,data,event['id'],gateway.live)
    elif kind in ('charge.refunded','charge.dispute.created','charge.dispute.closed'):
        intent = data.get('payment_intent')
        if isinstance(intent,str) and intent.startswith('pi_'):
            conn.execute('INSERT OR IGNORE INTO payment_adjustments(payment_intent) VALUES(?)',(intent,))
            if kind=='charge.refunded':
                amount=data.get('amount_refunded',0)
                if type(amount) is int and amount>=0:
                    conn.execute('UPDATE payment_adjustments SET refunded_cents=MAX(refunded_cents,?) WHERE payment_intent=?',(amount,intent))
            else:
                timestamp = event.get('created',0)
                if type(timestamp) is int:
                    disputed = 0 if kind=='charge.dispute.closed' and data.get('status')=='won' else 1
                    conn.execute('UPDATE payment_adjustments SET disputed=?,dispute_updated=? WHERE payment_intent=? AND dispute_updated<=?',(disputed,timestamp,intent,timestamp))
            adj=conn.execute('SELECT * FROM payment_adjustments WHERE payment_intent=?',(intent,)).fetchone()
            conn.execute('UPDATE online_payments SET refunded_cents=MIN(amount_cents,?),disputed=? WHERE payment_intent=?',(adj['refunded_cents'],adj['disputed'],intent))
            receipt=conn.execute('SELECT job_id FROM online_payments WHERE payment_intent=?',(intent,)).fetchone()
            if receipt:
                audit(conn,receipt['job_id'],'Payment provider','payment.updated',{'refunded_cents':adj['refunded_cents'],'under_review':bool(adj['disputed'])},True)
    conn.execute('INSERT INTO webhook_events VALUES(?,?,?)',(event['id'],kind,now()))
    return {'received':True}
