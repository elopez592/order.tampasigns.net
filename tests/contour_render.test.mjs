// Run with @napi-rs/canvas installed (or provided through NODE_PATH).
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {autoContourArtwork,renderSticker} from '../app/static/contour-artwork.js';
const {createCanvas,loadImage}=createRequire(import.meta.url)('@napi-rs/canvas');
globalThis.document={createElement:()=>createCanvas(1,1)};
const source=createCanvas(500,300),s=source.getContext('2d');
s.fillStyle='#faf9f7';s.fillRect(0,0,500,300);s.fillStyle='#111';
s.beginPath();s.moveTo(70,120);s.lineTo(170,35);s.lineTo(260,120);s.lineTo(340,20);s.lineTo(430,120);s.lineTo(395,120);s.lineTo(340,55);s.lineTo(265,145);s.lineTo(170,70);s.lineTo(105,120);s.fill();
s.font='bold 78px serif';s.fillText('BELLA',70,220);s.fillStyle='#b88932';s.font='bold 32px serif';s.fillText('HOMES',180,258);
const jpg=await loadImage(source.toBuffer('image/jpeg',55));
const detected=await autoContourArtwork(jpg);assert.equal(detected.method,'background');
const samples=[];
for(const shape of ['contour','circle','rectangle','rounded'])for(const mode of ['border','none']){
 const canvas=createCanvas(600,600),design={width:3,height:3,settings:{shape,border:.125,border_color:'#fff',border_mode:mode,scale:100}};
 renderSticker(canvas,detected.canvas,design,true);
 const data=canvas.getContext('2d').getImageData(0,0,600,600).data;
 const pink=(d,i)=>d[i]>190&&d[i+1]<70&&d[i+2]>60&&d[i+3]>0;
 let pinkCount=0;
 for(let i=0;i<data.length;i+=4)if(pink(data,i))pinkCount++;
 assert.ok(pinkCount,`${shape}/${mode} has a cut guide`);
 // Every pink pixel must be reachable from the exterior without crossing artwork.
 const seen=new Uint8Array(600*600),queue=[0];seen[0]=1;
 for(let head=0;head<queue.length;head++){
  const i=queue[head],x=i%600,y=Math.floor(i/600);
  for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){
   const nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=600||ny>=600)continue;
   const n=ny*600+nx;if(seen[n]||(data[n*4+3]>20&&!pink(data,n*4)))continue;
   seen[n]=1;queue.push(n);
  }
 }
 for(let i=0;i<seen.length;i++)if(pink(data,i*4))assert.ok(seen[i],`${shape}/${mode} has no internal cut guides`);
 const production=createCanvas(600,600);renderSticker(production,detected.canvas,design,false);
 const pd=production.getContext('2d').getImageData(0,0,600,600).data;
 for(let i=0;i<pd.length;i+=4)assert.ok(!pink(pd,i),'pink guide never prints');
 if(shape==='circle')assert.equal(pd[3],0,'circle corners stay outside');
 if(shape==='rectangle')assert.equal(pd[3],255,'rectangle fills its corner');
 samples.push(canvas);
}
// Equal dimensions give a true circle regardless of the wide source logo.
const circle=createCanvas(600,600);renderSticker(circle,detected.canvas,{width:3,height:3,settings:{shape:'circle',border_mode:'none',scale:100}},true);
const cd=circle.getContext('2d').getImageData(0,0,600,600).data;
assert.equal(cd[(300*600+100)*4+3],cd[(100*600+300)*4+3]);
if(process.env.CONTOUR_QA_IMAGE){
 const {writeFileSync}=await import('node:fs');const gallery=createCanvas(1200,600),g=gallery.getContext('2d');g.fillStyle='#e8eeee';g.fillRect(0,0,1200,600);
 samples.forEach((sample,i)=>g.drawImage(sample,(i%4)*300,Math.floor(i/4)*300,300,300));
 writeFileSync(process.env.CONTOUR_QA_IMAGE,gallery.toBuffer('image/png'));
}
console.log('Compressed JPG, shape geometry, zero border, and production-guide tests passed');
