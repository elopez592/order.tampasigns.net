import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {companyProductImage,companyProjects} from '../app/static/company-media.js';

const media=JSON.parse(await readFile(new URL('../app/company_setups/mirakol/media.json',import.meta.url),'utf8'));
assert.equal(Object.keys(media.products).length,40);
assert.equal(new Set(Object.values(media.products).map(item=>item.image)).size,40);
for(const [name,item] of Object.entries(media.products)){
  assert.equal(companyProductImage(media,{name}),item);
  const bytes=await readFile(new URL('../app'+item.image,import.meta.url));
  assert.equal(bytes.subarray(0,4).toString(),'RIFF',name+' has a valid WebP asset');
  assert.equal(bytes.subarray(8,12).toString(),'WEBP');
  assert.match(item.alt,/product mockup/);
}
assert.equal(companyProductImage({}, {name:'Custom T-shirts'}),null);
assert.notEqual(companyProductImage(media,{name:'Vehicle Wraps'}).image,companyProductImage(media,{name:'Partial Vehicle Wraps'}).image);
const tampa=[{slug:'vehicle-wraps',image:'/static/projects/real-work/service-van-wrap.webp'}];
assert.deepEqual(companyProjects(media,true,tampa),[],'Generated mockups never become real-work projects');
assert.equal(companyProjects(media,false,tampa),tampa,'Platform retains its existing real-work gallery');
const own=[{slug:'custom-t-shirts',image:'/static/projects/mirakol/real-work/shirt.webp'}];
assert.equal(companyProjects({projects:own},true,tampa),own,'A company uses only its own real-work projects');
console.log('PASS: 40 distinct Mirakol assets and company gallery isolation.');
