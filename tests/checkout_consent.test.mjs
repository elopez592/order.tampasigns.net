import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createCheckoutProof} from '../app/static/checkout-proof.js';

test('preview approval shares one required terms checkbox and resets when the artwork changes',async()=>{
  const label={textContent:''},button={textContent:''};
  const confirm={checked:false,required:true,closest:()=>({querySelector:()=>label})};
  const mode={value:'preview'};
  const form={elements:{confirm,artwork_approval_mode:mode,site_survey_requested:{checked:false},
    artwork:{files:[new File(['local artwork'],'items-1-ready.png',{type:'image/png'})]}},querySelector:()=>button};
  const fileInput={dataset:{proofFile:'0'},checked:true};
  const mappingInput={dataset:{proofIndex:'0',proofLine:'0'},checked:true};
  const target={isConnected:true,innerHTML:'',closest:()=>form,
    querySelectorAll:selector=>selector==='[data-proof-file]'?[fileInput]:[mappingInput]};
  const state={canBuy:true,currentQuoteItems:[{}],quote:{lines:[{name:'Foam boards',width:24,height:36,quantity:2}]},
    catalog:{approval_statement:'I approve this exact artwork and accept the terms.',job_terms:{confirmation:'I accept the terms.'}}};
  const original=globalThis.document;
  globalThis.document={querySelector:()=>target};
  const proof=createCheckoutProof({state,esc:value=>String(value),shop:()=>({designFiles:async()=>[]}),toast:()=>{}});
  try{
    await proof.refresh();
    assert.equal(target.innerHTML.includes('name="approve_uploads"'),false);
    assert.equal(confirm.required,true);
    assert.equal(label.textContent,state.catalog.approval_statement);
    assert.equal(button.textContent,'Approve artwork & go to payment');
    assert.throws(()=>proof.submission(form,true),/checkbox/);
    confirm.checked=true;
    const saved=proof.submission(form,true);
    assert.equal(saved.approve,true);
    assert.deepEqual(saved.files[0].line_indices,[0]);
    mappingInput.checked=false;mappingInput.onchange();
    assert.equal(confirm.checked,false);
    assert.deepEqual(saved.files[0].line_indices,[0]); // Submitted consent keeps its original mapping.
    mappingInput.checked=true;mappingInput.onchange();
    confirm.checked=true;mode.value='shop';mode.onchange();
    assert.equal(confirm.checked,false);
    assert.equal(label.textContent,state.catalog.job_terms.confirmation);
    assert.equal(proof.submission(form,true).approve,false);
    mode.value='preview';mode.onchange();
    confirm.checked=true;form.elements.site_survey_requested.checked=true;
    proof.resetApproval(form);proof.updateConsent(form);
    assert.equal(confirm.checked,false);
    assert.equal(label.textContent,state.catalog.job_terms.confirmation);
    assert.equal(button.textContent,'Submit project & request survey');
  }finally{proof.clear();globalThis.document=original;}
});
