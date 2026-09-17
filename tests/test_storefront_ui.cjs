// Run with: node tests/test_storefront_ui.cjs. No npm dependencies.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8');
const context = vm.createContext({document:{querySelector:()=>null}, console});
vm.runInContext(source.slice(0, source.indexOf('/* Customer-facing estimator */')), context);
const run = code => vm.runInContext(code, context);
let count=0;
function check(name, fn){fn();count++;console.log('PASS '+name);}
check('Starter labels are shortened',()=>assert.equal(run("storefrontName({name:'Roll / sheet labels'})"),'Labels'));
check('ACM title loses sidedness, not saved specifications',()=>assert.equal(run("storefrontName({name:'ACM sign - single sided'})"),'ACM sign'));
check('Custom owner product names are preserved',()=>assert.equal(run("storefrontName({name:'Premium 2-sided aluminum'})"),'Premium 2-sided aluminum'));
check('Icons do not depend on list position',()=>assert.equal(run("storefrontIcon({name:'Custom magnets'})"),'magnet'));
check('Wrap printing and installed wraps have different icons',()=>assert.notEqual(run("storefrontIcon({name:'Cast wrap film - print and laminate'})"),run("storefrontIcon({name:'Vehicle wrap - installed estimate'})")));
check('Ten product families have distinct icon types',()=>assert.equal(run("new Set(['Die-cut stickers','Roll / sheet labels','Custom magnets','Vinyl banner','ACM sign - single sided','Yard sign - single sided','Storefront perforated graphics','Acrylic sign face replacement','Cast wrap film - print and laminate','Vehicle wrap - installed estimate'].map(name=>storefrontIcon({name}))).size"),10));
check('Owner-authored descriptions survive',()=>assert.equal(run("storefrontDescription({config:{description:'Double-sided, pickup only.'}})"),'Double-sided, pickup only.'));
check('Standard products still have order intent in demo mode',()=>assert.equal(run("storefrontNeedsQuote({review_required:true,lines:[{review_required:false}]})"),false));
check('Custom and oversized work retain quote intent',()=>assert.equal(run("storefrontNeedsQuote({lines:[{review_required:true}]})"),true));
check('Mixed lines retain quote intent',()=>assert.equal(run("storefrontNeedsQuote({lines:[{review_required:false},{review_required:true}]})"),true));
check('Old CTA is gone',()=>assert.equal(source.includes('Request this project'),false));
check('Large public demonstration banner is gone',()=>assert.equal(source.includes('Pricing preview: these are editable demonstration rates'),false));
check('Staff demonstration-rate notice remains',()=>assert.ok(source.includes('Example rates are loaded for testing.')));
check('Server review and checkout availability still gate payment',()=>assert.ok(source.includes("canBuy=!q.review_required&&!!state.catalog.checkout?.available")));
check('Order confirmations disclose payment is not taken',()=>assert.ok(source.includes('No payment has been taken.')));
check('Product and quantity choices expose pressed state',()=>assert.ok(source.includes('aria-pressed="${p.id===product.id}"') && source.includes("b.setAttribute('aria-pressed',String(active))")));
check('Edits immediately invalidate pending estimates',()=>assert.ok(source.includes("if(event.target.closest('#calculator')){++state.calcSequence;state.canBuy=false;")));
check('Stale form values cannot open an order modal',()=>assert.ok(source.includes('JSON.stringify(currentItem())!==JSON.stringify(state.currentQuoteItem)')));
check('Product names are escaped in markup',()=>assert.ok(source.includes('${esc(storefrontName(p))}')));
check('Receipt title says Order received or Quote request received',()=>assert.ok(source.includes("showModal(state.orderReview?'Quote request received':'Order received',")));
console.log(count+' storefront contract checks passed');

