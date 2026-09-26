import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const app=await readFile(new URL('../app/static/app.js',import.meta.url),'utf8');
const shop=await readFile(new URL('../app/static/shop.js',import.meta.url),'utf8');
const styles=await readFile(new URL('../app/static/styles.css',import.meta.url),'utf8');

const projects=[
  'food-trailer-wrap','service-van-wrap','storefront-window-graphics',
  'directional-sign','vehicle-window-lettering','roadside-sign'
];

for(const name of projects){
  const asset=new URL(`../app/static/projects/real-work/${name}.webp`,import.meta.url);
  const bytes=await readFile(asset);
  assert.equal(bytes.subarray(0,4).toString(),'RIFF',`${name} should be a WebP asset`);
  assert.match(app,new RegExp(`/static/projects/real-work/${name}\\.webp`));
}

assert.match(shop,/realWorkGallery\(\)/,'All products should render the real-work gallery');
assert.match(app,/realWorkProductSection\(product\)/,'Matching product pages should render a secondary real-project panel');
assert.match(styles,/\.real-work-grid\{/,'The gallery should include its responsive layout');
assert.match(styles,/client-jobs\/vehicle-wraps\.webp/,'Existing primary product imagery should remain configured separately');

console.log('PASS: separate real-work assets, products gallery, matching detail panels and original product imagery.');
