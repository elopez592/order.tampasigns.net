import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const source=await readFile(new URL('../app/static/catalog-promos.js',import.meta.url),'utf8');
const {catalogPromo,mountCatalogPromo}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

class Element {
  constructor(dataset={}){this.dataset=dataset;this.attrs={};this.events=new Map();this.textContent='';}
  addEventListener(name,fn){if(!this.events.has(name))this.events.set(name,new Set());this.events.get(name).add(fn);}
  removeEventListener(name,fn){this.events.get(name)?.delete(fn);}
  emit(name,extra={}){const event={target:this,preventDefault(){this.prevented=true;},...extra};for(const fn of this.events.get(name)||[])fn(event);return event;}
  setAttribute(name,value){this.attrs[name]=value;}
  closest(selector){return selector==='[data-promo-index]'&&'promoIndex'in this.dataset||selector==='[data-promo-step]'&&'promoStep'in this.dataset||selector==='.catalog-promo-toggle'&&this.isToggle?this:null;}
}

function fixture(reduced=false){
  let time=0,id=0;const timers=new Map(),observers={};
  globalThis.setTimeout=(fn,ms)=>{timers.set(++id,{fn,at:time+ms});return id;};
  globalThis.clearTimeout=id=>timers.delete(id);
  const clock=ms=>{const end=time+ms;while(true){const next=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;time=next[1].at;timers.delete(next[0]);next[1].fn();}time=end;};
  for(const name of ['ResizeObserver','IntersectionObserver','MutationObserver']){
    globalThis[name]=class {constructor(fn){this.fn=fn;this.disconnected=false;observers[name]=this;}observe(){}disconnect(){this.disconnected=true;}};
  }
  const media=new Element();media.matches=reduced;
  globalThis.window={matchMedia:()=>media};
  const doc=new Element();doc.hidden=false;globalThis.document=doc;
  const root=new Element(),track=new Element(),toggle=new Element(),counter=new Element(),status=new Element(),app=new Element();
  root.isConnected=true;root.parentNode=app;root.closest=()=>app;
  toggle.isToggle=true;toggle.firstElementChild=new Element();
  track.clientWidth=390;track.scrollLeft=0;track.scrollTo=options=>{track.scrollLeft=options.left;track.lastScroll=options;track.emit('scroll');};
  const slides=Array.from({length:3},()=>new Element());
  const dots=Array.from({length:3},(_,i)=>new Element({promoIndex:String(i)}));
  root.querySelector=selector=>({'.catalog-promo-track':track,'.catalog-promo-toggle':toggle,'.catalog-promo-counter':counter,'.catalog-promo-status':status}[selector]);
  root.querySelectorAll=selector=>selector==='.catalog-promo-slide'?slides:dots;
  root.contains=target=>[root,track,toggle,...dots,...slides].includes(target);
  const dispose=mountCatalogPromo(root);
  return {root,track,toggle,counter,status,slides,dots,media,doc,clock,observers,timers,dispose,click:target=>root.emit('click',{target})};
}

const markup=catalogPromo();
assert.equal((markup.match(/aria-roledescription="slide"/g)||[]).length,3);
assert.equal((markup.match(/width="1200" height="480"/g)||[]).length,3,'Images reserve their intrinsic aspect ratio');
assert.match(markup,/Show vehicle wraps/);

{
  const f=fixture();
  f.clock(7000);assert.equal(f.counter.textContent,'2 / 3');assert.equal(f.track.scrollLeft,390);
  assert.equal(f.slides[0].inert,true);assert.equal(f.slides[1].inert,false);
  f.click(f.dots[2]);assert.equal(f.track.scrollLeft,780);assert.match(f.status.textContent,/Storefront/);
  f.clock(14000);assert.equal(f.counter.textContent,'3 / 3','Manual navigation pauses automatic rotation');
  f.click(new Element({promoStep:'1'}));assert.equal(f.counter.textContent,'1 / 3','Next wraps around');
  f.root.emit('keydown',{key:'ArrowLeft'});assert.equal(f.counter.textContent,'3 / 3');
  f.track.clientWidth=320;f.observers.ResizeObserver.fn();assert.equal(f.track.scrollLeft,640,'Resize preserves selected slide');
  f.dispose();assert.equal(f.timers.size,0);
}
{
  const f=fixture();
  f.track.emit('pointerdown');f.track.scrollLeft=780;f.track.emit('scroll');f.clock(200);
  assert.equal(f.counter.textContent,'3 / 3','Native swipe scrolling updates the controls');
  f.clock(14000);assert.equal(f.counter.textContent,'3 / 3','A swipe is not undone by autoplay');
  f.click(f.toggle);f.clock(7000);assert.equal(f.counter.textContent,'1 / 3','Play resumes automatic rotation');
  f.doc.hidden=true;f.doc.emit('visibilitychange');f.clock(14000);assert.equal(f.counter.textContent,'1 / 3');
  f.doc.hidden=false;f.doc.emit('visibilitychange');f.clock(7000);assert.equal(f.counter.textContent,'2 / 3');
  f.root.isConnected=false;f.observers.MutationObserver.fn();
  assert.equal(f.timers.size,0);assert.ok(Object.values(f.observers).every(x=>x.disconnected),'Navigation removes observers');
  assert.ok([...f.doc.events.values()].every(x=>x.size===0),'Navigation removes document listeners');
}
{
  const f=fixture(true);f.clock(21000);assert.equal(f.counter.textContent,'1 / 3','Reduced-motion preference disables autoplay');
  f.click(f.dots[1]);assert.equal(f.track.lastScroll.behavior,'instant');f.dispose();
}
{
  const f=fixture();f.root.emit('focusin',{target:f.track});f.root.emit('focusout',{relatedTarget:null});
  f.clock(14000);assert.equal(f.counter.textContent,'1 / 3','Keyboard interaction pauses autoplay until explicitly resumed');
  f.dispose();
}
console.log('PASS: carousel navigation, swipe settling, autoplay pause/resume, hidden tabs, resize, reduced motion and cleanup.');
