import assert from 'node:assert/strict';
import {test} from 'node:test';
import {belowCheckoutMinimum,minimumCheckoutMessage,submitOrderCheckout} from '../app/static/order-checkout.js';

const quote={review_required:false,meets_minimum_order:true,minimum_order_cents:3500,subtotal_cents:4048};
const payload={customer_name:'Local test',confirm:true,terms_version:'2026-09-30',reward_credit:'5',reward_points:'100'};
const review={approve:true,files:[{file:new File(['artwork'],'items-1-design.png',{type:'image/png'}),approved:true,line_indices:[0]}]};
function setup(failure='',changes={}){
  const calls=[],csrf=[];
  const api=async(path,method,data)=>{
    calls.push({path,method,data});
    if(path===failure)throw new Error('Local test failure');
    if(path==='/api/orders'||path==='/api/requests')return {job_id:42,number:'JOB-0042',portal_url:'http://example.test/portal#token=local-token',csrf:'local-csrf'};
    if(path==='/api/jobs/42/artwork')return {asset_id:7,sha256:'exact-upload-hash'};
    if(path==='/api/portal/checkout')return {url:'https://checkout.stripe.com/c/pay/local-fake-only'};
    return {ok:true};
  };
  return {calls,csrf,options:{api,setCsrf:value=>csrf.push(value),buy:true,quote,payload,review,...changes}};
}

test('approved instant previews and rewards proceed directly to one payment session',async()=>{
  const {calls,csrf,options}=setup();
  const result=await submitOrderCheckout(options);
  assert.deepEqual(calls.map(call=>call.path),['/api/orders','/api/jobs/42/artwork','/api/portal/artwork-preview/approve','/api/portal/rewards/apply','/api/portal/checkout']);
  assert.deepEqual(csrf,['local-csrf']);
  assert.deepEqual(calls[2].data.files,[{asset_id:7,sha256:'exact-upload-hash',line_indices:[0]}]);
  assert.equal(calls[2].data.confirm,true);
  assert.equal(result.artworkApproved,true);
  assert.equal(result.problem,'');
  assert.equal(result.checkout.url,'https://checkout.stripe.com/c/pay/local-fake-only');
  assert.equal(calls.some(call=>call.path.includes('accept-quote')),false);
});

test('the screenshot cart cannot become a quote request in the checkout path',async()=>{
  const small={...quote,subtotal_cents:2024,meets_minimum_order:false};
  assert.equal(belowCheckoutMinimum(small),true);
  assert.match(minimumCheckoutMessage(small),/\$35\.00.*\$14\.76/);
  const {options,calls}=setup('',{buy:false,quote:small});
  await assert.rejects(submitOrderCheckout(options),/\$35\.00.*\$14\.76/);
  assert.equal(calls.length,0);
  assert.equal(belowCheckoutMinimum({...small,review_required:true}),false);
});

test('a single explicit confirmation is required before creating the order',async()=>{
  const {options,calls}=setup('',{payload:{...payload,confirm:false}});
  await assert.rejects(submitOrderCheckout(options),/artwork and terms/);
  assert.equal(calls.length,0);
});

for(const path of ['/api/jobs/42/artwork','/api/portal/artwork-preview/approve','/api/portal/rewards/apply']){
  test('failure at '+path+' retains the order and stops payment',async()=>{
    const {options,calls}=setup(path);
    const result=await submitOrderCheckout(options);
    assert.equal(result.order.job_id,42);
    assert.match(result.problem,/Local test failure/);
    assert.equal(result.checkout,null);
    assert.equal(result.paymentFailed,false);
    assert.equal(calls.some(call=>call.path==='/api/portal/checkout'),false);
    assert.equal(result.artworkApproved,path==='/api/portal/rewards/apply');
  });
}

test('payment failure preserves the already-approved proof for a payment-only retry',async()=>{
  const {options,calls}=setup('/api/portal/checkout');
  const result=await submitOrderCheckout(options);
  assert.equal(result.order.job_id,42);
  assert.equal(result.artworkApproved,true);
  assert.equal(result.paymentFailed,true);
  assert.match(result.problem,/payment could not open/);
  assert.equal(calls.filter(call=>call.path==='/api/portal/artwork-preview/approve').length,1);
});

test('a missing payment URL is recoverable without a second artwork approval',async()=>{
  const {options}=setup();
  const api=options.api;
  options.api=(...args)=>args[0]==='/api/portal/checkout'?Promise.resolve({}):api(...args);
  const result=await submitOrderCheckout(options);
  assert.equal(result.artworkApproved,true);
  assert.equal(result.paymentFailed,true);
  assert.match(result.problem,/payment link was not returned/);
});

test('survey and custom quote requests save files and never start checkout',async()=>{
  const {options,calls}=setup('',{buy:false,quote:{...quote,review_required:true},review:{...review,approve:false}});
  const result=await submitOrderCheckout(options);
  assert.deepEqual(calls.map(call=>call.path),['/api/requests','/api/jobs/42/artwork']);
  assert.equal(result.checkout,null);
  assert.equal(result.artworkApproved,false);
});

test('a fully covered order follows the existing zero-payment return URL',async()=>{
  const {options}=setup();const api=options.api;
  options.api=(...args)=>args[0]==='/api/portal/checkout'?Promise.resolve({paid:true,url:'http://example.test/portal?payment=received'}):api(...args);
  const result=await submitOrderCheckout(options);
  assert.equal(result.checkout.paid,true);
  assert.equal(result.paymentFailed,false);
  assert.equal(result.checkout.url,'http://example.test/portal?payment=received');
});
