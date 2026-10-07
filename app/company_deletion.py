"""Owner-confirmed company removal, billing cutoff, and retained recovery data."""
from fastapi import Body, Depends, HTTPException
from .db import transaction, audit, now


def object_id(value):
    return value.get('id') if isinstance(value, dict) else value


def stop_billing(app, row, pending):
    gateway = app.state.subscription_gateway
    subscriptions = set(filter(None, [row['stripe_subscription']]))
    if pending:
        session = gateway.call('checkout.sessions', 'retrieve', identifier=pending['session_id'])
        if (session.get('id') != pending['session_id'] or session.get('mode') != 'subscription'
                or object_id(session.get('customer')) != row['stripe_customer']
                or session.get('client_reference_id') != row['slug']):
            raise HTTPException(409, 'Checkout ownership needs review before this company can be deleted.')
        if session.get('status') == 'open':
            session = gateway.call('checkout.sessions', 'expire', identifier=pending['session_id'])
        if session.get('status') not in ('expired', 'complete'):
            raise HTTPException(502, 'Checkout has not stopped. Company was not deleted; retry shortly.')
        subscription = object_id(session.get('subscription'))
        if subscription:
            subscriptions.add(subscription)
        elif session.get('status') == 'complete':
            raise HTTPException(409, 'Checkout is still processing. Wait for billing confirmation before deleting.')
    # Retrieve and verify every subscription before canceling any of them.
    verified = []
    for identifier in sorted(subscriptions):
        subscription = gateway.subscription(identifier)
        if (subscription.get('id') != identifier or not row['stripe_customer']
                or object_id(subscription.get('customer')) != row['stripe_customer']):
            raise HTTPException(409, 'Subscription ownership needs review before this company can be deleted.')
        verified.append(subscription)
    for subscription in verified:
        if subscription.get('status') not in ('canceled', 'incomplete_expired'):
            canceled = gateway.call('subscriptions', 'cancel', {'invoice_now': False, 'prorate': False},
                                     identifier=subscription['id'])
            if (canceled.get('id') != subscription['id'] or canceled.get('status') != 'canceled'
                    or object_id(canceled.get('customer')) != row['stripe_customer']):
                raise HTTPException(502, 'Subscription cancellation is not confirmed. Company was not deleted; retry shortly.')
    return sorted(subscriptions)


def install(app, owner):
    @app.delete('/api/platform/companies/{slug}')
    def remove(slug: str, payload: dict = Body(...), user=Depends(owner)):
        if payload.get('confirm_slug') != slug:
            raise HTTPException(422, 'Type the exact company ID to confirm deletion.')
        if type(payload.get('cancel_billing', False)) is not bool:
            raise HTTPException(422, 'Confirm the billing cancellation choice.')
        # Serializes removal with checkout creation and subscription webhooks.
        with app.state.subscription_lock:
            with transaction(app.state.database) as conn:
                found = conn.execute('SELECT * FROM platform_companies WHERE slug=?', (slug,)).fetchone()
                pending = conn.execute('SELECT * FROM subscription_checkout WHERE slug=?', (slug,)).fetchone()
            if not found:
                raise HTTPException(404, 'Company not found.')
            row = dict(found)
            if row['deleted_at']:
                return {'ok': True, 'already_deleted': True, 'records_retained': True}
            if type(payload.get('revision')) is not int or payload['revision'] != row['revision']:
                raise HTTPException(409, 'Company changed. Reload before deleting.')
            if (row['stripe_subscription'] or pending) and not payload.get('cancel_billing'):
                raise HTTPException(409, 'Confirm cancellation of subscription billing and open checkout before deleting.')
            canceled = stop_billing(app, row, pending) if row['stripe_subscription'] or pending else []
            with transaction(app.state.database, True) as conn:
                current = conn.execute('SELECT * FROM platform_companies WHERE slug=?', (slug,)).fetchone()
                if current['revision'] != row['revision']:
                    raise HTTPException(409, 'Company changed during billing cancellation. Reload and retry deletion.')
                conn.execute("UPDATE platform_companies SET status='closed',deleted_at=?,updated_at=?,revision=revision+1,"
                             "subscription_status=CASE WHEN billing_mode='stripe' THEN 'canceled' ELSE subscription_status END,"
                             "grace_until=0,cancel_at_period_end=0 WHERE slug=?", (now(), now(), slug))
                conn.execute('DELETE FROM platform_support_grants WHERE slug=?', (slug,))
                conn.execute('DELETE FROM subscription_checkout WHERE slug=?', (slug,))
                audit(conn, None, user['email'], 'platform.company_deleted',
                      {'slug': slug, 'name': row['name'], 'subscriptions_stopped': canceled, 'records_retained': True})
            app.state.company_apps.pop(slug, None)
        return {'ok': True, 'billing_stopped': bool(canceled), 'records_retained': True}
