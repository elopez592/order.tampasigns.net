const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));

function distanceSq(data,offset,color){
  const dr=data[offset]-color[0],dg=data[offset+1]-color[1],db=data[offset+2]-color[2];
  return dr*dr+dg*dg+db*db;
}

function boundsFor(mask,width,height){
  let left=width,top=height,right=-1,bottom=-1,count=0;
  for(let y=0;y<height;y++){
    for(let x=0;x<width;x++){
      const i=y*width+x;
      if(!mask[i])continue;
      count++;
      if(x<left)left=x;if(x>right)right=x;if(y<top)top=y;if(y>bottom)bottom=y;
    }
  }
  if(right<left||bottom<top)return {left:0,top:0,right:width-1,bottom:height-1,count:0};
  return {left,top,right,bottom,count};
}

function opaqueResult(width,height,reason='uncertain'){
  const mask=new Uint8Array(width*height);mask.fill(255);
  return {mask,bounds:{left:0,top:0,right:width-1,bottom:height-1,count:width*height},method:'opaque',backgroundDetected:false,confidence:0,reason};
}

function median(values){
  if(!values.length)return 0;
  const sorted=[...values].sort((a,b)=>a-b),middle=Math.floor(sorted.length/2);
  return sorted.length%2?sorted[middle]:(sorted[middle-1]+sorted[middle])/2;
}

function robustBackground(data,width,height){
  const patch=Math.max(2,Math.min(32,Math.round(Math.min(width,height)*.045))),samples=[];
  const sampleRect=(x0,y0,x1,y1)=>{
    const step=Math.max(1,Math.floor(Math.max(x1-x0,y1-y0)/18));
    for(let y=y0;y<y1;y+=step)for(let x=x0;x<x1;x+=step){
      const offset=(y*width+x)*4;
      if(data[offset+3]<245)continue;
      samples.push([data[offset],data[offset+1],data[offset+2]]);
    }
  };
  sampleRect(0,0,patch,patch);sampleRect(width-patch,0,width,patch);
  sampleRect(0,height-patch,patch,height);sampleRect(width-patch,height-patch,width,height);
  if(samples.length<8)return null;
  const color=[median(samples.map(v=>v[0])),median(samples.map(v=>v[1])),median(samples.map(v=>v[2]))];
  const distances=samples.map(v=>Math.hypot(v[0]-color[0],v[1]-color[1],v[2]-color[2])).sort((a,b)=>a-b);
  return {color,p90:distances[Math.min(distances.length-1,Math.floor(distances.length*.9))]||0};
}

export function buildAutoMask(imageData,width,height,options={}){
  const data=imageData?.data||imageData,total=width*height,sensitivity=clamp(Number(options.sensitivity)||1,.65,1.65);
  if(!data||data.length<total*4||!width||!height)return opaqueResult(Math.max(1,width||1),Math.max(1,height||1),'invalid');

  let transparent=0;
  for(let i=3;i<data.length;i+=4)if(data[i]<248)transparent++;
  if(transparent>=Math.max(12,Math.round(total*.0005))){
    const mask=new Uint8Array(total);
    for(let i=0,p=0;i<data.length;i+=4,p++)mask[p]=data[i+3]>12?255:0;
    const bounds=boundsFor(mask,width,height);
    if(bounds.count<Math.max(8,total*.002))return opaqueResult(width,height,'alpha-empty');
    return {mask,bounds,method:'alpha',backgroundDetected:true,confidence:1,reason:'transparent-alpha'};
  }

  const robust=robustBackground(data,width,height),samples=[],bins=new Map();
  const addSample=index=>{
    const offset=index*4,r=data[offset],g=data[offset+1],b=data[offset+2],key=(r>>5)*64+(g>>5)*8+(b>>5);
    samples.push([r,g,b,key]);
    bins.set(key,(bins.get(key)||0)+1);
  };
  const edgeStep=Math.max(1,Math.floor(Math.max(width,height)/900));
  for(let x=0;x<width;x+=edgeStep){addSample(x);if(height>1)addSample((height-1)*width+x);}
  for(let y=edgeStep;y<height-edgeStep;y+=edgeStep){addSample(y*width);if(width>1)addSample(y*width+width-1);}
  if(!samples.length)return opaqueResult(width,height,'no-edge-samples');

  let dominantKey=null,dominantCount=0;
  for(const [key,count] of bins)if(count>dominantCount){dominantKey=key;dominantCount=count;}
  const dominant=samples.filter(sample=>sample[3]===dominantKey),dominantRatio=dominantCount/samples.length;
  if(dominantRatio<.08&&!robust)return opaqueResult(width,height,'mixed-edge-background');

  let bg,p90;
  if(robust){
    bg=robust.color;p90=robust.p90;
  }else{
    bg=[0,0,0];
    for(const sample of dominant){bg[0]+=sample[0];bg[1]+=sample[1];bg[2]+=sample[2];}
    bg[0]/=dominant.length;bg[1]/=dominant.length;bg[2]/=dominant.length;
    const deviations=dominant.map(sample=>Math.hypot(sample[0]-bg[0],sample[1]-bg[1],sample[2]-bg[2])).sort((a,b)=>a-b);
    p90=deviations[Math.min(deviations.length-1,Math.floor(deviations.length*.9))]||0;
  }

  const strictTolerance=clamp((16+p90*1.35)*sensitivity,16,78),looseTolerance=clamp((32+p90*2.5)*sensitivity,30,138);
  const strictSq=strictTolerance*strictTolerance,looseSq=looseTolerance*looseTolerance;
  const bgLuma=.2126*bg[0]+.7152*bg[1]+.0722*bg[2],bgChroma=Math.max(...bg)-Math.min(...bg);
  const background=new Uint8Array(total),queue=new Int32Array(total);
  let head=0,tail=0;
  const similar=(index,thresholdSq)=>{
    const offset=index*4;
    if(distanceSq(data,offset,bg)<=thresholdSq)return true;
    const r=data[offset],g=data[offset+1],b=data[offset+2],luma=.2126*r+.7152*g+.0722*b,chroma=Math.max(r,g,b)-Math.min(r,g,b);
    return bgLuma>210&&Math.abs(luma-bgLuma)<=42*sensitivity&&chroma<=Math.max(28,bgChroma+24)*sensitivity;
  };
  const seed=index=>{
    if(background[index]||!similar(index,strictSq))return;
    background[index]=1;queue[tail++]=index;
  };
  for(let x=0;x<width;x++){seed(x);seed((height-1)*width+x);}
  for(let y=1;y<height-1;y++){seed(y*width);seed(y*width+width-1);}

  while(head<tail){
    const index=queue[head++],x=index%width,y=Math.floor(index/width);
    for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
      if(!dx&&!dy)continue;
      const nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=width||ny>=height)continue;
      const neighbor=ny*width+nx;
      if(background[neighbor]||!similar(neighbor,looseSq))continue;
      background[neighbor]=1;queue[tail++]=neighbor;
    }
  }

  let mask=new Uint8Array(total);
  let foregroundCount=0;
  for(let i=0;i<total;i++){if(!background[i]){mask[i]=255;foregroundCount++;}}
  const foregroundRatio=foregroundCount/total,removedRatio=1-foregroundRatio;
  if(foregroundRatio<.005||foregroundRatio>.985||removedRatio<.015)return opaqueResult(width,height,'background-not-separable');

  mask=componentFilter(mask,width,height);
  const bounds=boundsFor(mask,width,height),confidence=clamp(.5+Math.max(.12,dominantRatio)*.35+Math.min(.14,removedRatio*.16),.5,.99);
  return {mask,bounds,method:'background',backgroundDetected:true,confidence,reason:'edge-connected-background',backgroundColor:bg,tolerance:looseTolerance};
}

function componentFilter(mask,width,height){
  const total=width*height,seen=new Uint8Array(total),queue=new Int32Array(total),components=[];
  for(let start=0;start<total;start++){
    if(!mask[start]||seen[start])continue;
    let head=0,tail=0;queue[tail++]=start;seen[start]=1;const pixels=[];
    while(head<tail){
      const index=queue[head++],x=index%width,y=Math.floor(index/width);pixels.push(index);
      for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
        if(!dx&&!dy)continue;const nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=width||ny>=height)continue;
        const neighbor=ny*width+nx;if(!mask[neighbor]||seen[neighbor])continue;seen[neighbor]=1;queue[tail++]=neighbor;
      }
    }
    components.push(pixels);
  }
  if(!components.length)return mask;
  components.sort((a,b)=>b.length-a.length);
  const threshold=Math.max(4,Math.round(components[0].length*.0015),Math.round(total*.000015)),out=new Uint8Array(total);
  for(const pixels of components){if(pixels.length<threshold)continue;for(const index of pixels)out[index]=255;}
  return out;
}

function dilateStep(mask,width,height){
  const out=new Uint8Array(mask.length);
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    let on=0;
    for(let dy=-1;dy<=1&&!on;dy++)for(let dx=-1;dx<=1;dx++){
      const nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=width||ny>=height)continue;
      if(mask[ny*width+nx]){on=255;break;}
    }
    out[y*width+x]=on;
  }
  return out;
}
function erodeStep(mask,width,height){
  const out=new Uint8Array(mask.length);
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    let on=255;
    for(let dy=-1;dy<=1&&on;dy++)for(let dx=-1;dx<=1;dx++){
      const nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=width||ny>=height||!mask[ny*width+nx]){on=0;break;}
    }
    out[y*width+x]=on;
  }
  return out;
}
function fillHoles(mask,width,height){
  const total=width*height,out=new Uint8Array(mask),outside=new Uint8Array(total),queue=new Int32Array(total);let head=0,tail=0;
  const seed=index=>{if(mask[index]||outside[index])return;outside[index]=1;queue[tail++]=index;};
  for(let x=0;x<width;x++){seed(x);seed((height-1)*width+x);}
  for(let y=1;y<height-1;y++){seed(y*width);seed(y*width+width-1);}
  while(head<tail){
    const index=queue[head++],x=index%width,y=Math.floor(index/width);
    for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
      if(!dx&&!dy)continue;const nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=width||ny>=height)continue;
      const next=ny*width+nx;if(mask[next]||outside[next])continue;outside[next]=1;queue[tail++]=next;
    }
  }
  for(let i=0;i<total;i++)if(!mask[i]&&!outside[i])out[i]=255;
  return out;
}

export function buildSilhouetteMask(imageData,width,height,{joinRadius=0}={}){
  const data=imageData?.data||imageData,total=width*height,mask=new Uint8Array(total);
  if(!data)return mask;
  if(data.length===total){for(let i=0;i<total;i++)mask[i]=data[i]?255:0;}
  else for(let i=0;i<total;i++)mask[i]=data[i*4+3]>20?255:0;
  let out=componentFilter(mask,width,height),radius=clamp(Math.round(joinRadius),0,28);
  if(radius){
    for(let i=0;i<radius;i++)out=dilateStep(out,width,height);
    for(let i=0;i<radius;i++)out=erodeStep(out,width,height);
  }
  // A die-cut sticker is one solid piece. Join lettering across each scanline;
  // do not turn the spaces between letters into internal cutting paths.
  const labels=new Int32Array(total),queue=new Int32Array(total);let label=0,joinStart=height;
  for(let start=0;start<total;start++){
    if(!out[start]||labels[start])continue;
    label++;let head=0,tail=0;queue[tail++]=start;labels[start]=label;
    while(head<tail){
      const i=queue[head++],x=i%width,y=Math.floor(i/width);
      for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
        const nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=width||ny>=height)continue;
        const n=ny*width+nx;if(!out[n]||labels[n])continue;labels[n]=label;queue[tail++]=n;
      }
    }
  }
  for(let y=0;y<height;y++){
    let first=0;
    for(let x=0;x<width;x++){
      const id=labels[y*width+x];if(!id)continue;
      if(first&&id!==first){joinStart=Math.min(joinStart,y);break;}first=id;
    }
  }
  let previous=null;
  for(let y=0;y<height;y++){
    let left=width,right=-1;
    for(let x=0;x<width;x++)if(out[y*width+x]){left=Math.min(left,x);right=x;}
    if(right<0)continue;
    if(previous&&y>previous.y+1){
      for(let row=previous.y+1;row<y;row++){
        const t=(row-previous.y)/(y-previous.y);
        const a=Math.floor(previous.left+(left-previous.left)*t),b=Math.ceil(previous.right+(right-previous.right)*t);
        out.fill(255,row*width+a,row*width+b+1);
      }
    }
    if(y>=joinStart)out.fill(255,y*width+left,y*width+right+1);
    previous={y,left,right};
  }
  // Bridge stacked logo/text groups without thin necks or deep notches.
  for(let x=0;x<width;x++){
    let top=height,bottom=-1;
    for(let y=0;y<height;y++)if(out[y*width+x]){top=Math.min(top,y);bottom=y;}
    for(let y=top;y<=bottom;y++)out[y*width+x]=255;
  }
  for(let y=0;y<height;y++){
    let left=width,right=-1;
    for(let x=0;x<width;x++)if(out[y*width+x]){left=Math.min(left,x);right=x;}
    if(right>=0&&y>=joinStart)out.fill(255,y*width+left,y*width+right+1);
  }
  out=fillHoles(out,width,height);
  return componentFilter(out,width,height);
}

export async function autoContourArtwork(source,{maskMaxDimension=900,sensitivity=1}={}){
  const sourceWidth=Math.max(1,source.naturalWidth||source.videoWidth||source.width||1);
  const sourceHeight=Math.max(1,source.naturalHeight||source.videoHeight||source.height||1);
  const maskScale=Math.min(1,maskMaxDimension/Math.max(sourceWidth,sourceHeight));
  const work=document.createElement('canvas');
  work.width=Math.max(1,Math.round(sourceWidth*maskScale));
  work.height=Math.max(1,Math.round(sourceHeight*maskScale));
  const workContext=work.getContext('2d',{willReadFrequently:true});
  workContext.imageSmoothingEnabled=true;workContext.imageSmoothingQuality='high';
  workContext.drawImage(source,0,0,work.width,work.height);

  const detected=buildAutoMask(workContext.getImageData(0,0,work.width,work.height),work.width,work.height,{sensitivity});
  const pad=detected.backgroundDetected?2:0;
  const left=Math.max(0,detected.bounds.left-pad),top=Math.max(0,detected.bounds.top-pad);
  const right=Math.min(work.width-1,detected.bounds.right+pad),bottom=Math.min(work.height-1,detected.bounds.bottom+pad);
  const scaleX=sourceWidth/work.width,scaleY=sourceHeight/work.height;
  const sourceLeft=Math.max(0,Math.floor(left*scaleX)),sourceTop=Math.max(0,Math.floor(top*scaleY));
  const sourceRight=Math.min(sourceWidth,Math.ceil((right+1)*scaleX)),sourceBottom=Math.min(sourceHeight,Math.ceil((bottom+1)*scaleY));

  const output=document.createElement('canvas');
  output.width=Math.max(1,sourceRight-sourceLeft);
  output.height=Math.max(1,sourceBottom-sourceTop);
  const out=output.getContext('2d');
  out.imageSmoothingEnabled=true;out.imageSmoothingQuality='high';
  out.drawImage(source,sourceLeft,sourceTop,output.width,output.height,0,0,output.width,output.height);

  if(detected.backgroundDetected){
    const maskCanvas=document.createElement('canvas');maskCanvas.width=work.width;maskCanvas.height=work.height;
    const maskContext=maskCanvas.getContext('2d'),maskImage=maskContext.createImageData(work.width,work.height);
    for(let i=0;i<detected.mask.length;i++){
      const offset=i*4;
      maskImage.data[offset]=255;maskImage.data[offset+1]=255;maskImage.data[offset+2]=255;maskImage.data[offset+3]=detected.mask[i];
    }
    maskContext.putImageData(maskImage,0,0);
    out.save();out.globalCompositeOperation='destination-in';out.imageSmoothingEnabled=true;out.imageSmoothingQuality='high';
    out.drawImage(maskCanvas,left,top,right-left+1,bottom-top+1,0,0,output.width,output.height);out.restore();
  }

  return {canvas:output,method:detected.method,backgroundDetected:detected.backgroundDetected,confidence:detected.confidence,reason:detected.reason};
}

// Smooth raster stair steps at a scale proportional to the sticker artwork.
export function smoothMask(mask,width,height,radius=2){
  const r=Math.max(1,Math.round(radius)),span=2*r+1;
  let values=Float32Array.from(mask),temp=new Float32Array(mask.length);
  for(let pass=0;pass<3;pass++){
    for(let y=0;y<height;y++){
      let sum=0;for(let x=0;x<=r&&x<width;x++)sum+=values[y*width+x];
      for(let x=0;x<width;x++){
        temp[y*width+x]=sum/span;
        if(x-r>=0)sum-=values[y*width+x-r];
        if(x+r+1<width)sum+=values[y*width+x+r+1];
      }
    }
    for(let x=0;x<width;x++){
      let sum=0;for(let y=0;y<=r&&y<height;y++)sum+=temp[y*width+x];
      for(let y=0;y<height;y++){
        values[y*width+x]=sum/span;
        if(y-r>=0)sum-=temp[(y-r)*width+x];
        if(y+r+1<height)sum+=temp[(y+r+1)*width+x];
      }
    }
  }
  return Uint8Array.from(values,v=>v>=127.5?255:0);
}

// Linear-time distance field, avoiding shifted alpha stamps and their seams.
export function expandMask(mask,width,height,radius){
  if(radius<=0)return new Uint8Array(mask);
  const distance=new Float32Array(mask.length),diagonal=Math.SQRT2;
  for(let i=0;i<mask.length;i++)distance[i]=mask[i]?0:1e9;
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const i=y*width+x;
    if(x)distance[i]=Math.min(distance[i],distance[i-1]+1);
    if(y){distance[i]=Math.min(distance[i],distance[i-width]+1);
      if(x)distance[i]=Math.min(distance[i],distance[i-width-1]+diagonal);
      if(x+1<width)distance[i]=Math.min(distance[i],distance[i-width+1]+diagonal);}
  }
  for(let y=height-1;y>=0;y--)for(let x=width-1;x>=0;x--){
    const i=y*width+x;
    if(x+1<width)distance[i]=Math.min(distance[i],distance[i+1]+1);
    if(y+1<height){distance[i]=Math.min(distance[i],distance[i+width]+1);
      if(x)distance[i]=Math.min(distance[i],distance[i+width-1]+diagonal);
      if(x+1<width)distance[i]=Math.min(distance[i],distance[i+width+1]+diagonal);}
  }
  return Uint8Array.from(distance,d=>d<=radius?255:0);
}

export function renderSticker(canvas,artwork,design,proof=true){
  const c=canvas.getContext('2d'),w=canvas.width,h=canvas.height,s=design.settings;
  c.clearRect(0,0,w,h);if(!artwork)return;
  const margin=proof?Math.min(w,h)*.13:0;
  const boxW=w-2*margin,boxH=h-2*margin;
  const pxPerInch=Math.min(boxW/Number(design.width||3),boxH/Number(design.height||3));
  const border=s.border_mode==='none'?0:Math.max(0,Number(s.border??.125))*pxPerInch;
  const innerW=Math.max(1,boxW-border*2),innerH=Math.max(1,boxH-border*2);
  const layer=document.createElement('canvas');layer.width=w;layer.height=h;
  const l=layer.getContext('2d',{willReadFrequently:true});
  // An ellipse must contain the whole fitted artwork at 100%, including corners.
  const fit=s.shape==='circle'?Math.SQRT1_2:1;
  const scale=Math.min(innerW/artwork.width,innerH/artwork.height)*fit*Number(s.scale??100)/100;
  const iw=artwork.width*scale,ih=artwork.height*scale;
  l.drawImage(artwork,(w-iw)/2,(h-ih)/2,iw,ih);
  const cut=document.createElement('canvas');cut.width=w;cut.height=h;const m=cut.getContext('2d',{willReadFrequently:true});
  let mask;
  if(s.shape==='contour'){
    const silhouette=buildSilhouetteMask(l.getImageData(0,0,w,h),w,h,{joinRadius:Math.min(14,Math.max(2,Math.round(Math.min(iw,ih)*.012)))});
    mask=expandMask(smoothMask(silhouette,w,h,Math.max(1,Math.min(iw,ih)*.008)),w,h,border);
  }else{
    m.fillStyle='#fff';m.beginPath();
    if(s.shape==='circle')m.ellipse(w/2,h/2,boxW/2,boxH/2,0,0,Math.PI*2);
    else if(s.shape==='rounded')m.roundRect(margin,margin,boxW,boxH,Math.min(boxW,boxH)*.08);
    else m.rect(margin,margin,boxW,boxH);
    m.fill();const rgba=m.getImageData(0,0,w,h).data;
    mask=Uint8Array.from({length:w*h},(_,i)=>rgba[i*4+3]);
  }
  const color=s.border_color||'#ffffff';
  const paintMask=(target,alpha,fill)=>{
    const context=target.getContext('2d'),pixels=context.createImageData(w,h);
    for(let i=0;i<alpha.length;i++){pixels.data[i*4]=255;pixels.data[i*4+1]=255;pixels.data[i*4+2]=255;pixels.data[i*4+3]=alpha[i];}
    context.putImageData(pixels,0,0);context.globalCompositeOperation='source-in';context.fillStyle=fill;context.fillRect(0,0,w,h);context.globalCompositeOperation='source-over';
  };
  paintMask(cut,mask,color);
  if(proof){
    const outer=expandMask(mask,w,h,Math.max(2,Math.min(w,h)*.004));
    const ring=Uint8Array.from(outer,(a,i)=>mask[i]?0:a);
    const line=document.createElement('canvas');line.width=w;line.height=h;paintMask(line,ring,'#d81b60');c.drawImage(line,0,0);
  }
  // Solid substrate inside the cut; the pink proof guide never enters print art.
  c.drawImage(cut,0,0);
  l.globalCompositeOperation='destination-in';l.drawImage(cut,0,0);c.drawImage(layer,0,0);
}
