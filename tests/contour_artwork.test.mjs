import assert from 'node:assert/strict';
import {buildAutoMask,buildSilhouetteMask} from '../app/static/contour-artwork.js';

function image(width,height,background=[250,250,250,255]){
  const data=new Uint8ClampedArray(width*height*4);
  for(let i=0;i<width*height;i++)data.set(background,i*4);
  return data;
}
function paint(data,width,x0,y0,x1,y1,color){
  for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++)data.set(color,(y*width+x)*4);
}

{
  const width=20,height=20,data=image(width,height);
  paint(data,width,5,4,15,17,[40,90,50,255]);
  const result=buildAutoMask({data},width,height);
  assert.equal(result.backgroundDetected,true);
  assert.equal(result.method,'background');
  assert.ok(result.bounds.left<=5&&result.bounds.right>=14);
  assert.ok(result.bounds.top<=4&&result.bounds.bottom>=16);
  assert.equal(result.mask[0],0);
  assert.equal(result.mask[10*width+10],255);
}

{
  const width=12,height=12,data=image(width,height,[0,0,0,0]);
  paint(data,width,3,2,10,11,[30,60,90,255]);
  const result=buildAutoMask({data},width,height);
  assert.equal(result.backgroundDetected,true);
  assert.equal(result.method,'alpha');
  assert.equal(result.mask[0],0);
  assert.equal(result.mask[6*width+6],255);
}

{
  const width=16,height=16,data=image(width,height,[80,80,80,255]);
  for(let x=0;x<width;x++)data.set(x%2?[245,245,245,255]:[20,20,20,255],x*4);
  const result=buildAutoMask({data},width,height);
  assert.equal(typeof result.backgroundDetected,'boolean');
}
console.log('contour artwork mask tests passed');


{
  const width=24,height=24,rgba=new Uint8ClampedArray(width*height*4);
  for(let y=7;y<12;y++)for(let x=5;x<10;x++)rgba[(y*width+x)*4+3]=255;
  for(let y=7;y<12;y++)for(let x=13;x<18;x++)rgba[(y*width+x)*4+3]=255;
  const silhouette=buildSilhouetteMask({data:rgba},width,height,{joinRadius:2});
  assert.equal(silhouette[9*width+11],255,'nearby artwork islands should unite into one sticker silhouette');
}

{
  const width=20,height=20,data=image(width,height,[247,246,243,255]);
  paint(data,width,4,4,16,16,[30,30,30,255]);
  // JPEG-like warm edge noise should still be treated as background.
  for(let x=0;x<width;x++){data.set([239+(x%3),238,236,255],x*4);data.set([241,239+(x%2),237,255],((height-1)*width+x)*4);}
  const result=buildAutoMask({data},width,height);
  assert.equal(result.backgroundDetected,true);
  assert.equal(result.mask[10*width+10],255);
  assert.equal(result.mask[0],0);
}
