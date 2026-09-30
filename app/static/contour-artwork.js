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

export function buildAutoMask(imageData,width,height){
  const data=imageData?.data||imageData,total=width*height;
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

  const samples=[],bins=new Map();
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
  const dominant=samples.filter(sample=>sample[3]===dominantKey);
  const dominantRatio=dominantCount/samples.length;
  if(dominantRatio<.12)return opaqueResult(width,height,'mixed-edge-background');

  const bg=[0,0,0];
  for(const sample of dominant){bg[0]+=sample[0];bg[1]+=sample[1];bg[2]+=sample[2];}
  bg[0]/=dominant.length;bg[1]/=dominant.length;bg[2]/=dominant.length;

  const deviations=dominant.map(sample=>{
    const dr=sample[0]-bg[0],dg=sample[1]-bg[1],db=sample[2]-bg[2];
    return Math.sqrt(dr*dr+dg*dg+db*db);
  }).sort((a,b)=>a-b);
  const p90=deviations[Math.min(deviations.length-1,Math.floor(deviations.length*.9))]||0;
  const tolerance=clamp(24+p90*2.2,28,92),toleranceSq=tolerance*tolerance;

  const background=new Uint8Array(total),queue=new Int32Array(total);
  let head=0,tail=0;
  const seed=index=>{
    if(background[index])return;
    const offset=index*4;
    if(distanceSq(data,offset,bg)>toleranceSq)return;
    background[index]=1;queue[tail++]=index;
  };
  for(let x=0;x<width;x++){seed(x);seed((height-1)*width+x);}
  for(let y=1;y<height-1;y++){seed(y*width);seed(y*width+width-1);}

  while(head<tail){
    const index=queue[head++],x=index%width;
    const visit=neighbor=>{
      if(neighbor<0||neighbor>=total||background[neighbor])return;
      const offset=neighbor*4;
      if(distanceSq(data,offset,bg)>toleranceSq)return;
      background[neighbor]=1;queue[tail++]=neighbor;
    };
    if(index>=width)visit(index-width);
    if(index<total-width)visit(index+width);
    if(x>0)visit(index-1);
    if(x<width-1)visit(index+1);
  }

  const mask=new Uint8Array(total);
  let foregroundCount=0;
  for(let i=0;i<total;i++){if(!background[i]){mask[i]=255;foregroundCount++;}}
  const foregroundRatio=foregroundCount/total,removedRatio=1-foregroundRatio;
  if(foregroundRatio<.005||foregroundRatio>.985||removedRatio<.015)return opaqueResult(width,height,'background-not-separable');

  const bounds=boundsFor(mask,width,height);
  const confidence=clamp(.45+dominantRatio*.45+Math.min(.1,removedRatio*.12),.45,.99);
  return {mask,bounds,method:'background',backgroundDetected:true,confidence,reason:'edge-connected-background',backgroundColor:bg,tolerance};
}

export async function autoContourArtwork(source,{maskMaxDimension=900}={}){
  const sourceWidth=Math.max(1,source.naturalWidth||source.videoWidth||source.width||1);
  const sourceHeight=Math.max(1,source.naturalHeight||source.videoHeight||source.height||1);
  const maskScale=Math.min(1,maskMaxDimension/Math.max(sourceWidth,sourceHeight));
  const work=document.createElement('canvas');
  work.width=Math.max(1,Math.round(sourceWidth*maskScale));
  work.height=Math.max(1,Math.round(sourceHeight*maskScale));
  const workContext=work.getContext('2d',{willReadFrequently:true});
  workContext.imageSmoothingEnabled=true;workContext.imageSmoothingQuality='high';
  workContext.drawImage(source,0,0,work.width,work.height);

  const detected=buildAutoMask(workContext.getImageData(0,0,work.width,work.height),work.width,work.height);
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
