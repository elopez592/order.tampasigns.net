import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createRewards} from '../app/static/rewards.js';

function rewardsUI({signedIn=false,enabled=true,bonus=50}={}) {
  const program={enabled,first_order_bonus_points:bonus,points_per_dollar:'1',point_value_cents:1,terms:'Local program terms'};
  const wallet={program,credit_cents:0,points:0,points_value_cents:0,history:[]};
  const state={customer:signedIn?{id:1}:null,catalog:{rewards:program}};
  const ui=createRewards({state,api:async()=>({wallet}),esc:String,money:value=>'$'+(value/100).toFixed(2),
    date:String,input:()=>'',actions:{},forms:{}});
  return {ui,wallet};
}

test('guest checkout explains the live bonus without literal template expressions',async()=>{
  const {ui}=rewardsUI({bonus:75});
  const html=await ui.checkoutBox();
  assert.match(html,/Sign in to earn points/);
  assert.match(html,/Plus 75 bonus points on your first paid order/);
  assert.doesNotMatch(html,/\$\{/);
});

test('account and signed-in checkout show the bonus alongside ordinary earnings',async()=>{
  const {ui,wallet}=rewardsUI({signedIn:true});
  const account=ui.accountBox(wallet);
  assert.match(account,/Earn 1 point\(s\) per eligible dollar paid/);
  assert.match(account,/Plus 50 bonus points on your first paid order/);
  assert.match(await ui.checkoutBox(),/Plus 50 bonus points on your first paid order/);
});

test('paused rewards do not advertise an active first-order bonus',async()=>{
  for (const signedIn of [false,true]) {
    const {ui,wallet}=rewardsUI({signedIn,enabled:false});
    assert.doesNotMatch(await ui.checkoutBox(),/bonus points/);
    assert.doesNotMatch(ui.accountBox(wallet),/bonus points/);
  }
});
