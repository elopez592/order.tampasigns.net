// A visual embroidery approximation. Original artwork is always kept for shop digitizing.
const MAX_BYTES = 50 * 1024 * 1024;
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
export const embroidered = product => ['embroidered_polo','embroidered_hat','embroidered_hoodie'].includes(product?.config?.apparel_kind);
export const embroideryLimits = (product, placement) => {
  const option = product.config.placement_options.find(p => p.id === placement);
  if (!option) throw new Error('Choose a valid embroidery placement.');
  return {width: Number(option.width), height: Number(option.height), offset: placement === 'front' ? .35 : .75};
};
const chestSide = placement => ['left_chest','right_chest'].includes(placement);
const oppositeChest = placement => placement === 'left_chest' ? 'right_chest' : placement === 'right_chest' ? 'left_chest' : '';
const placementLabel = placement => placement.replace('_',' ');

function dominantColors(canvas) {
  const {data} = canvas.getContext('2d', {willReadFrequently:true}).getImageData(0, 0, canvas.width, canvas.height);
  const buckets = new Map();
  for (let i = 0; i < data.length; i += 16) {
    if (data[i + 3] < 100) continue;
    const rgb = [data[i], data[i + 1], data[i + 2]].map(c => Math.round(c / 32) * 32);
    const key = rgb.join(',');
    const entry = buckets.get(key) || {rgb:[0,0,0], n:0};
    entry.rgb[0] += data[i]; entry.rgb[1] += data[i+1]; entry.rgb[2] += data[i+2]; entry.n++;
    buckets.set(key, entry);
  }
  const chosen = [];
  for (const entry of [...buckets.values()].sort((a,b) => b.n - a.n)) {
    const rgb = entry.rgb.map(v => Math.round(v / entry.n));
    if (chosen.every(other => rgb.reduce((sum,v,i) => sum + (v-other[i]) ** 2, 0) > 2500)) chosen.push(rgb);
    if (chosen.length === 6) break;
  }
  return (chosen.length ? chosen : [[255,255,255]]).map(rgb => '#' + rgb.map(v => v.toString(16).padStart(2,'0')).join(''));
}

const toRgb = hex => [1,3,5].map(i => parseInt(hex.slice(i,i+2),16));
export function visibleArtworkBounds(data, width, height, alphaThreshold = 20) {
  let left = width, right = -1, top = height, bottom = -1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (data[(y * width + x) * 4 + 3] <= alphaThreshold) continue;
      left = Math.min(left, x); right = Math.max(right, x);
      top = Math.min(top, y); bottom = Math.max(bottom, y);
    }
  }
  return right < left ? null : {left, top, width:right - left + 1, height:bottom - top + 1};
}

export function artworkAspectRatio(image) {
  return image?.dataset?.artworkWidth && image?.dataset?.artworkHeight
    ? Number(image.dataset.artworkWidth) / Number(image.dataset.artworkHeight)
    : image.width / image.height;
}

function drawThread(context, image, width, height, colors, x, y) {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width)); canvas.height = Math.max(1, Math.round(height));
  const c = canvas.getContext('2d', {willReadFrequently:true});
  c.drawImage(image, 0, 0, canvas.width, canvas.height);
  const frame = c.getImageData(0,0,canvas.width,canvas.height), pixels = frame.data;
  const palette = colors.map(toRgb);
  for (let i=0; i<pixels.length; i+=4) {
    if (pixels[i+3] < 36) { pixels[i+3]=0; continue; }
    let nearest=palette[0], distance=Infinity;
    for (const rgb of palette) {
      const d=(pixels[i]-rgb[0])**2+(pixels[i+1]-rgb[1])**2+(pixels[i+2]-rgb[2])**2;
      if (d<distance) {distance=d;nearest=rgb;}
    }
    const px=(i/4)%canvas.width, py=Math.floor(i/4/canvas.width);
    const shine=Math.sin((px+py*.6)*2.6)*5 + Math.sin(py*.75)*2;
    for (let j=0;j<3;j++) pixels[i+j]=clamp(nearest[j]+shine,0,255);
  }
  c.putImageData(frame,0,0);
  context.save();context.shadowColor='rgba(5,12,20,.28)';context.shadowBlur=1;context.shadowOffsetY=.5;
  context.drawImage(canvas,x,y);context.restore();
  // Short diagonal highlights are clipped to the logo's nontransparent pixels.
  const sheen=document.createElement('canvas');sheen.width=canvas.width;sheen.height=canvas.height;
  const s=sheen.getContext('2d');s.strokeStyle='rgba(255,255,255,.12)';s.lineWidth=1;
  for(let row=-canvas.width;row<canvas.height+canvas.width;row+=4){
    s.beginPath();s.moveTo(0,row);s.lineTo(canvas.width,row-canvas.width*.35);s.stroke();
  }
  s.globalCompositeOperation='destination-in';s.drawImage(canvas,0,0);
  context.drawImage(sheen,x,y);
}

function drawThreadText(context, text, centerX, centerY, ppi) {
  const lines = [text?.line1, text?.line2].map(line => String(line || '').trim()).filter(Boolean).slice(0, 2);
  if (!lines.length) return;
  const width = clamp(Number(text.width) || 3, .75, 3.5) * ppi;
  const color = /^#[0-9a-fA-F]{6}$/.test(text.thread_color || '') ? text.thread_color : '#ffffff';
  const fontFamily = 'Arial, Helvetica, sans-serif';
  context.save();
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  let size = lines.length === 1 ? 19 : 15;
  for (; size >= 8; size--) {
    context.font = `700 ${size}px ${fontFamily}`;
    if (Math.max(...lines.map(line => context.measureText(line).width)) <= width) break;
  }
  const lineHeight = size * 1.2;
  const top = centerY - (lineHeight * (lines.length - 1)) / 2;
  context.shadowColor = 'rgba(5,12,20,.28)';
  context.shadowBlur = 1;
  context.shadowOffsetY = .5;
  context.fillStyle = color;
  context.strokeStyle = 'rgba(255,255,255,.16)';
  context.lineWidth = .6;
  lines.forEach((line, index) => {
    const y = top + index * lineHeight;
    context.strokeText(line, centerX, y);
    context.fillText(line, centerX, y);
  });
  context.restore();
}

// Generated product photographs. Tint the photographed fabric while preserving its texture.
const PHOTO_LAYOUTS = {
  embroidered_polo: {file:'polo-photo.webp', chestX:.63, chestY:.34, ppi:17},
  embroidered_hoodie: {file:'hoodie-photo.webp', chestX:.62, chestY:.37, ppi:16},
  embroidered_hat: {file:'hat-photo.webp', chestX:.5, chestY:.43, ppi:62},
};
const photoLoads = new Map(), photoTints = new Map(), renderVersions = new WeakMap();
function loadPhoto(kind) {
  if (!PHOTO_LAYOUTS[kind]) throw new Error('Choose a polo, hat or hoodie for embroidery.');
  if (!photoLoads.has(kind)) {
    const image = new Image();
    image.src = '/static/products/embroidery/' + PHOTO_LAYOUTS[kind].file;
    photoLoads.set(kind, image.decode().then(() => image).catch(() => {
      photoLoads.delete(kind);
      throw new Error('The garment photo could not load. Refresh the page to try again.');
    }));
  }
  return photoLoads.get(kind);
}
function tintedPhoto(image, kind, color) {
  const key = kind + color;
  if (photoTints.has(key)) return photoTints.get(key);
  const canvas = document.createElement('canvas');canvas.width=800;canvas.height=800;
  const c=canvas.getContext('2d',{willReadFrequently:true});
  c.drawImage(image,0,0,800,800);
  const frame=c.getImageData(0,0,800,800), pixels=frame.data, rgb=toRgb(color);
  for(let i=0;i<pixels.length;i+=4){
    if(!pixels[i+3])continue;
    const light=(pixels[i]*.2126+pixels[i+1]*.7152+pixels[i+2]*.0722);
    const shade=Math.pow(light/245,2), highlight=Math.max(0,light-210)*.3;
    for(let j=0;j<3;j++) pixels[i+j]=clamp(rgb[j]*shade+highlight*(1-rgb[j]/255),0,255);
  }
  c.putImageData(frame,0,0);
  if(photoTints.size>=18)photoTints.delete(photoTints.keys().next().value);
  photoTints.set(key,canvas);return canvas;
}

export async function renderEmbroidery(canvas, product, fileImage, design, color, caption=false) {
  const version=(renderVersions.get(canvas)||0)+1;renderVersions.set(canvas,version);
  const kind=product.config.apparel_kind, layout=PHOTO_LAYOUTS[kind];
  const photo=await loadPhoto(kind);
  if(renderVersions.get(canvas)!==version)return;
  const c=canvas.getContext('2d'), sx=canvas.width/800, sy=canvas.height/(caption?760:680);
  c.save();c.scale(sx,sy);
  c.fillStyle='#f4f5f6';c.fillRect(0,0,800,caption?760:680);
  c.drawImage(tintedPhoto(photo,kind,color),80,12,640,640);
  const centerX=80+(design.placement==='right_chest'?1-layout.chestX:layout.chestX)*640;
  const centerY=12+layout.chestY*640, ppi=layout.ppi;
  const width=design.width*ppi, height=design.height*ppi;
  const x=centerX+design.offset_x*ppi-width/2, y=centerY+design.offset_y*ppi-height/2;
  if(fileImage && design.thread_colors?.length)drawThread(c,fileImage,width,height,design.thread_colors,x,y);
  if(design.text?.enabled && chestSide(design.text.placement)){
    const textX=80+(design.text.placement==='right_chest'?1-layout.chestX:layout.chestX)*640;
    drawThreadText(c,design.text,textX,centerY,ppi);
  }
  c.fillStyle='#5c6770';c.font='14px Arial, sans-serif';c.textAlign='center';
  const detail = design.text?.enabled ? `${placementLabel(design.placement)} logo + ${placementLabel(design.text.placement)} text` : placementLabel(design.placement);
  c.fillText(fileImage?`${design.width.toFixed(2)} × ${design.height.toFixed(2)} in  ·  ${detail}`:'Upload your logo to preview it here',400,666);
  if(caption){
    c.fillStyle='#ffffff';c.fillRect(0,680,800,80);c.fillStyle='#293f4b';c.font='15px Arial, sans-serif';
    c.fillText('Digital mockup. Garment style, thread colors and final details may vary.',400,712);
    c.fillText('Original artwork must be digitized and approved before production.',400,740);
  }
  c.restore();
}

const imageFrom = async file => {
  const url=URL.createObjectURL(file), image=new Image();
  try {
    image.src=url;await image.decode();
    if (!image.width || image.width*image.height>50_000_000) throw new Error('The logo is empty or exceeds 50 megapixels.');
    const raw=document.createElement('canvas');raw.width=image.width;raw.height=image.height;
    const rawContext=raw.getContext('2d',{willReadFrequently:true});
    rawContext.drawImage(image,0,0);
    const bounds=visibleArtworkBounds(rawContext.getImageData(0,0,raw.width,raw.height).data,raw.width,raw.height);
    const source=bounds || {left:0,top:0,width:image.width,height:image.height};
    const scale=Math.min(1,640/Math.max(source.width,source.height));
    const canvas=document.createElement('canvas');
    canvas.width=Math.max(1,Math.round(source.width*scale));canvas.height=Math.max(1,Math.round(source.height*scale));
    canvas.dataset.artworkWidth=String(source.width);
    canvas.dataset.artworkHeight=String(source.height);
    canvas.getContext('2d').drawImage(raw,source.left,source.top,source.width,source.height,0,0,canvas.width,canvas.height);
    return canvas;
  } finally {URL.revokeObjectURL(url);}
};

export function createEmbroidery(ctx) {
  const {getDesign,saveDesign,product,esc,toast,onChange}=ctx;
  const idFor=id=>`embroidery-draft-${id}`;
  let draft=null, image=null, currentId=null, zoomRefresh=()=>{};
  const $=selector=>document.querySelector(selector);
  const fileCheck=file=>{
    if(!file || !/\.(png|jpe?g)$/i.test(file.name) || !['image/png','image/jpeg'].includes(file.type)) throw new Error('Choose a PNG or JPG logo for the live preview. You may attach a PDF separately to your project.');
    if(!file.size || file.size>MAX_BYTES) throw new Error('Logo files must be nonempty and at most 50 MB.');
  };
  function defaultDesign(p) {
    return {placement:p.config.placement_options[0].id,width:p.config.apparel_kind==='embroidered_hat'?2.75:3,
      height:p.config.apparel_kind==='embroidered_hat'?1.4:3,offset_x:0,offset_y:0,thread_colors:['#ffffff'],
      text:{enabled:false,placement:'',line1:'',line2:'',width:3,thread_color:'#ffffff'}};
  }
  function normalizeText(p) {
    draft.design.text ||= {enabled:false,placement:'',line1:'',line2:'',width:3,thread_color:'#ffffff'};
    const text=draft.design.text, other=oppositeChest(draft.design.placement);
    const hasOther=other && p.config.placement_options.some(option=>option.id===other);
    if(!hasOther) text.enabled=false;
    text.placement=hasOther?other:'';
    text.line1=String(text.line1||'').slice(0,40);
    text.line2=String(text.line2||'').slice(0,40);
    text.width=clamp(Number(text.width)||3,.75,hasOther?embroideryLimits(p,other).width:3.5);
    if(!/^#[0-9a-fA-F]{6}$/.test(text.thread_color||'')) text.thread_color=draft.design.thread_colors?.[0]||'#ffffff';
    return hasOther;
  }
  const colorFor=p=>p.config.shirt_colors[$('#calculator')?.elements.shirt_color?.value]||'#ffffff';
  function sync(p) {
    if(!draft)return;
    const supportsOtherText=normalizeText(p);
    const max=embroideryLimits(p,draft.design.placement);
    const ratio=image ? artworkAspectRatio(image) : 1;
    if(Math.min(max.width,max.height*ratio)<Math.max(.5,.2*ratio)){
      throw new Error('This logo is too narrow or wide for the selected embroidery area.');
    }
    draft.design.width=clamp(Number(draft.design.width)||3.5,.5,Math.min(max.width,max.height*ratio));
    draft.design.height=Math.round(draft.design.width/ratio*100)/100;
    draft.design.offset_x=clamp(Number(draft.design.offset_x)||0,-max.offset,max.offset);
    draft.design.offset_y=clamp(Number(draft.design.offset_y)||0,-max.offset,max.offset);
    const size=$('#embroidery-width'),position=$('#embroidery-position');
    if(size){size.max=Math.min(max.width,max.height*ratio).toFixed(2);size.value=draft.design.width;}
    if(position)position.textContent=`${draft.design.width.toFixed(2)} × ${draft.design.height.toFixed(2)} in  ·  Max ${max.width} × ${max.height} in`;
    for(const axis of ['x','y']){const slider=$(`#embroidery-offset-${axis}`);if(slider){slider.min=-max.offset;slider.max=max.offset;slider.value=draft.design[`offset_${axis}`];}}
    const swatches=$('#embroidery-threads');if(swatches)swatches.innerHTML=draft.design.thread_colors.map((color,i)=>`<label class="embroidery-thread"><span>Thread ${i+1}</span><input type="color" data-thread="${i}" value="${esc(color)}"></label>`).join('');
    const textBlock=$('#embroidery-text-block'),textEnabled=$('#embroidery-text-enabled'),textSide=$('#embroidery-text-side'),textWidth=$('#embroidery-text-width'),textSize=$('#embroidery-text-size'),textColor=$('#embroidery-text-color');
    if(textBlock)textBlock.hidden=!supportsOtherText;
    if(textEnabled)textEnabled.checked=!!draft.design.text.enabled;
    const textLineCount=[draft.design.text.line1,draft.design.text.line2].filter(line=>String(line||'').trim()).length;
    if(textSide)textSide.textContent=supportsOtherText?`Adds ${placementLabel(draft.design.text.placement)} embroidery text · $7 per populated line${textLineCount?' (+: 'Text embroidery is available on polo and hoodie chest placements.';
    for(const field of ['line1','line2']){const node=$(`#embroidery-text-${field}`);if(node&&node.value!==draft.design.text[field])node.value=draft.design.text[field];}
    if(textWidth){textWidth.max=supportsOtherText?embroideryLimits(p,draft.design.text.placement).width:3.5;textWidth.value=draft.design.text.width; textWidth.disabled=!draft.design.text.enabled;}
    if(textSize)textSize.textContent=`${Number(draft.design.text.width).toFixed(2)} in text width`;
    if(textColor){textColor.value=draft.design.text.thread_color;textColor.disabled=!draft.design.text.enabled;}
    const canvas=$('#embroidery-canvas');if(canvas)renderEmbroidery(canvas,p,image,draft.design,colorFor(p)).then(()=>zoomRefresh()).catch(error=>toast(error.message,true));
    const status=$('#embroidery-file-status');if(status)status.textContent=draft.original?`${draft.original.name} saved for your project`:'Upload a logo to see the stitched preview.';
  }
  async function setup(p) {
    const preview=$('.product-preview');
    zoomRefresh=()=>{};
    if(preview){
      preview.onpointerenter=null;preview.onpointermove=null;preview.onpointerleave=null;preview.onwheel=null;
      preview.classList.remove('embroidery-product-preview');
    }
    if(!embroidered(p) || !preview)return;
    currentId=p.id;draft=null;image=null;const f=$('#calculator');
    preview.classList.add('embroidery-product-preview');
    preview.innerHTML='<canvas id="embroidery-canvas" width="800" height="680" aria-label="Digital embroidery mockup on the selected garment"></canvas><div id="embroidery-zoom-window" class="embroidery-zoom-window" aria-hidden="true"><canvas id="embroidery-zoom-canvas" width="260" height="260" aria-label="Magnified embroidery preview"></canvas><span id="embroidery-zoom-level" class="embroidery-zoom-level">2.3×</span></div>';
    f.insertAdjacentHTML('beforeend',`<section class="embroidery-controls"><h3>Preview your embroidery</h3><p class="field-hint">Upload a PNG or JPG logo (up to 50 MB). A transparent PNG gives the clearest stitch preview. Hover over the mockup for a magnified window. Scroll while hovering to zoom that window in or out. Use Finished embroidery width below to change the actual embroidery size.</p><label class="field mt-sm"><span>Logo for embroidery</span><input id="embroidery-upload" type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg"></label><p class="field-hint" id="embroidery-file-status" role="status"></p><label class="field mt-sm"><span>Finished embroidery width</span><input id="embroidery-width" type="range" min="0.5" step="0.05"><strong id="embroidery-position"></strong></label><div class="fields mt-sm"><label class="field"><span>Move horizontally</span><input id="embroidery-offset-x" type="range" step="0.05"></label><label class="field"><span>Move vertically</span><input id="embroidery-offset-y" type="range" step="0.05"></label></div><div class="field mt-sm"><span>Approximate thread colors</span><div id="embroidery-threads" class="embroidery-threads"></div></div><div id="embroidery-text-block" class="embroidery-extra mt-sm" hidden><label class="check"><input id="embroidery-text-enabled" type="checkbox"><span>Add name/title text on the other chest side (+$7 per line per garment)</span></label><p class="field-hint" id="embroidery-text-side"></p><div class="fields mt-sm"><label class="field"><span>Text line 1 — +$7 each</span><input id="embroidery-text-line1" type="text" maxlength="40" placeholder="Name"></label><label class="field"><span>Text line 2 optional — +$7 each</span><input id="embroidery-text-line2" type="text" maxlength="40" placeholder="Title"></label></div><label class="field mt-sm"><span>Text embroidery width</span><input id="embroidery-text-width" type="range" min="0.75" step="0.05"><strong id="embroidery-text-size"></strong></label><label class="embroidery-thread mt-sm"><span>Text thread</span><input id="embroidery-text-color" type="color"></label></div><p class="field-hint mt-sm">Garment style and thread colors are approximate. We will review your original logo and text and send a proof before production.</p></section>`);
    const [saved]=await Promise.all([getDesign(idFor(p.id)),loadPhoto(p.config.apparel_kind)]);
    if(currentId!==p.id || !$('#embroidery-canvas'))return;
    draft=saved||{id:idFor(p.id),kind:'embroidery-preview',product_id:p.id,original:null,design:defaultDesign(p)};
    try {image=draft.original?await imageFrom(draft.original):null;} catch {image=null;draft.original=null;toast('Saved logo could not be opened. Upload it again.',true);}
    const selected=[...f.querySelectorAll('input[name="print_locations"]')].find(input=>input.value===draft.design.placement);
    if(selected)selected.checked=true;
    sync(p);
    onChange();
    const sourceCanvas=$('#embroidery-canvas'),zoomWindow=$('#embroidery-zoom-window'),zoomCanvas=$('#embroidery-zoom-canvas'),zoomLabel=$('#embroidery-zoom-level');
    let zoomLevel=2.25,zoomClientX=null,zoomClientY=null;
    const drawZoom=()=>{
      if(!sourceCanvas||!zoomCanvas||!zoomWindow?.classList.contains('active'))return;
      const sourceRect=sourceCanvas.getBoundingClientRect(),zoomRect=zoomCanvas.getBoundingClientRect();
      if(!sourceRect.width||!sourceRect.height||!zoomRect.width||!zoomRect.height)return;
      const localX=zoomClientX===null?sourceRect.width/2:clamp(zoomClientX-sourceRect.left,0,sourceRect.width);
      const localY=zoomClientY===null?sourceRect.height/2:clamp(zoomClientY-sourceRect.top,0,sourceRect.height);
      const centerX=localX/sourceRect.width*sourceCanvas.width,centerY=localY/sourceRect.height*sourceCanvas.height;
      const sourceWidth=Math.min(sourceCanvas.width,zoomRect.width*(sourceCanvas.width/sourceRect.width)/zoomLevel);
      const sourceHeight=Math.min(sourceCanvas.height,zoomRect.height*(sourceCanvas.height/sourceRect.height)/zoomLevel);
      const sx=clamp(centerX-sourceWidth/2,0,Math.max(0,sourceCanvas.width-sourceWidth));
      const sy=clamp(centerY-sourceHeight/2,0,Math.max(0,sourceCanvas.height-sourceHeight));
      const z=zoomCanvas.getContext('2d');z.clearRect(0,0,zoomCanvas.width,zoomCanvas.height);z.imageSmoothingEnabled=true;z.imageSmoothingQuality='high';
      z.drawImage(sourceCanvas,sx,sy,sourceWidth,sourceHeight,0,0,zoomCanvas.width,zoomCanvas.height);
      if(zoomLabel)zoomLabel.textContent=`${zoomLevel.toFixed(1)}×`;
    };
    const showZoom=event=>{
      if(!sourceCanvas||!zoomWindow||!zoomCanvas)return;
      if(event&&Number.isFinite(event.clientX)){zoomClientX=event.clientX;zoomClientY=event.clientY;}
      zoomWindow.classList.add('active');zoomWindow.setAttribute('aria-hidden','false');drawZoom();
    };
    const hideZoom=()=>{if(zoomWindow){zoomWindow.classList.remove('active');zoomWindow.setAttribute('aria-hidden','true');}};
    preview.onpointerenter=showZoom;
    preview.onpointermove=event=>{zoomClientX=event.clientX;zoomClientY=event.clientY;showZoom(event);};
    preview.onpointerleave=hideZoom;
    preview.onwheel=event=>{
      event.preventDefault();event.stopPropagation();
      zoomClientX=event.clientX;zoomClientY=event.clientY;
      const step=event.deltaY<0?1.18:1/1.18;
      zoomLevel=clamp(zoomLevel*step,1.25,6);
      showZoom(event);
    };
    zoomRefresh=drawZoom;
    $('#embroidery-upload').onchange=async event=>{
      try {
        const file=event.target.files[0];if(!file)return;fileCheck(file);
        const decoded=await imageFrom(file);
        const limits=embroideryLimits(p,draft.design.placement),ratio=artworkAspectRatio(decoded);
        if(Math.min(limits.width,limits.height*ratio)<Math.max(.5,.2*ratio)) throw new Error('This logo is too narrow or wide for the selected embroidery area.');
        image=decoded;draft.original=file;
        draft.design.thread_colors=dominantColors(decoded);
        await saveDesign(draft);sync(p);onChange();
        window.TampaAnalytics?.track('upload_file');
      } catch(error){toast(error.message,true);} finally {event.target.value='';}
    };
    $('#embroidery-width').oninput=e=>{draft.design.width=Number(e.target.value);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));};
    $('#embroidery-text-enabled').onchange=e=>{draft.design.text.enabled=e.target.checked;sync(p);saveDesign(draft).catch(error=>toast(error.message,true));onChange();};
    for(const field of ['line1','line2'])$(`#embroidery-text-${field}`).oninput=e=>{draft.design.text[field]=e.target.value;draft.design.text.enabled=!!(draft.design.text.line1||draft.design.text.line2);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));onChange();};
    $('#embroidery-text-width').oninput=e=>{draft.design.text.width=Number(e.target.value);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));onChange();};
    $('#embroidery-text-color').oninput=e=>{draft.design.text.thread_color=e.target.value;sync(p);saveDesign(draft).catch(error=>toast(error.message,true));onChange();};
    for(const axis of ['x','y'])$(`#embroidery-offset-${axis}`).oninput=e=>{draft.design[`offset_${axis}`]=Number(e.target.value);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));};
    f.addEventListener('change',event=>{
      if(!$('#embroidery-canvas')||currentId!==p.id)return;
      if(event.target.name==='print_locations'){draft.design.placement=event.target.value;draft.design.offset_x=0;draft.design.offset_y=0;normalizeText(p);saveDesign(draft).catch(error=>toast(error.message,true));}
      if(event.target.dataset.thread!==undefined){draft.design.thread_colors[Number(event.target.dataset.thread)]=event.target.value;saveDesign(draft).catch(error=>toast(error.message,true));}
      sync(p);onChange();
    });
  }
  const selection=()=>draft?.original && draft.product_id===currentId && draft.design.width>=.5 && draft.design.height>=.2 ? structuredClone(draft.design):null;
  async function prepareItems(items) {
    for(const item of items){
      if(!embroidered(product(item.product_id)))continue;
      if(!draft?.original || currentId!==item.product_id)throw new Error('Upload your logo to create an embroidery preview before adding this garment.');
      const id=crypto.randomUUID();await saveDesign({...draft,id,design:structuredClone(draft.design)});
      item.embroidery_id=id;item.embroidery_preview=structuredClone(draft.design);
    }
    return items;
  }
  async function filesFor(items) {
    const files=[];
    for(let index=0;index<items.length;index++){
      const item=items[index],p=product(item.product_id);if(!embroidered(p))continue;
      if(!item.embroidery_id || !item.embroidery_preview)throw new Error(`The logo preview for item ${index+1} is missing. Remove and add that garment again.`);
      const record=await getDesign(item.embroidery_id);
      if(!record?.original)throw new Error(`The original embroidery logo for item ${index+1} is missing. Remove and add that garment again.`);
      fileCheck(record.original);
      const image=await imageFrom(record.original),canvas=document.createElement('canvas');canvas.width=1000;canvas.height=950;
      const selectedColor=p.config.shirt_colors[item.shirt_color]||'#ffffff';
      await renderEmbroidery(canvas,p,image,item.embroidery_preview,selectedColor,true);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
      if(!blob)throw new Error('Unable to save the embroidery preview. Please try again.');
      const suffix=/\.png$/i.test(record.original.name)?'png':'jpg';
      files.push(new File([record.original],`item-${index+1}-original-embroidery-logo.${suffix}`,{type:record.original.type}));
      files.push(new File([blob],`item-${index+1}-digital-embroidery-preview.png`,{type:'image/png'}));
    }
    return files;
  }
  async function show(item) {
    const p=product(item.product_id),record=await getDesign(item.embroidery_id);
    if(!record?.original)throw new Error('The saved embroidery preview is missing. Remove and add this item again.');
    const image=await imageFrom(record.original),canvas=$('#embroidery-modal-canvas');
    if(canvas)await renderEmbroidery(canvas,p,image,item.embroidery_preview,p.config.shirt_colors[item.shirt_color]||'#ffffff');
  }
  return {setup,selection,prepareItems,filesFor,show};
}
+(textLineCount*7)+' per garment)':''}`: 'Text embroidery is available on polo and hoodie chest placements.';
    for(const field of ['line1','line2']){const node=$(`#embroidery-text-${field}`);if(node&&node.value!==draft.design.text[field])node.value=draft.design.text[field];}
    if(textWidth){textWidth.max=supportsOtherText?embroideryLimits(p,draft.design.text.placement).width:3.5;textWidth.value=draft.design.text.width; textWidth.disabled=!draft.design.text.enabled;}
    if(textSize)textSize.textContent=`${Number(draft.design.text.width).toFixed(2)} in text width`;
    if(textColor){textColor.value=draft.design.text.thread_color;textColor.disabled=!draft.design.text.enabled;}
    const canvas=$('#embroidery-canvas');if(canvas)renderEmbroidery(canvas,p,image,draft.design,colorFor(p)).then(()=>zoomRefresh()).catch(error=>toast(error.message,true));
    const status=$('#embroidery-file-status');if(status)status.textContent=draft.original?`${draft.original.name} saved for your project`:'Upload a logo to see the stitched preview.';
  }
  async function setup(p) {
    const preview=$('.product-preview');
    zoomRefresh=()=>{};
    if(preview){
      preview.onpointerenter=null;preview.onpointermove=null;preview.onpointerleave=null;preview.onwheel=null;
      preview.classList.remove('embroidery-product-preview');
    }
    if(!embroidered(p) || !preview)return;
    currentId=p.id;draft=null;image=null;const f=$('#calculator');
    preview.classList.add('embroidery-product-preview');
    preview.innerHTML='<canvas id="embroidery-canvas" width="800" height="680" aria-label="Digital embroidery mockup on the selected garment"></canvas><div id="embroidery-zoom-window" class="embroidery-zoom-window" aria-hidden="true"><canvas id="embroidery-zoom-canvas" width="260" height="260" aria-label="Magnified embroidery preview"></canvas><span id="embroidery-zoom-level" class="embroidery-zoom-level">2.3×</span></div>';
    f.insertAdjacentHTML('beforeend',`<section class="embroidery-controls"><h3>Preview your embroidery</h3><p class="field-hint">Upload a PNG or JPG logo (up to 50 MB). A transparent PNG gives the clearest stitch preview. Hover over the mockup for a magnified window. Scroll while hovering to zoom that window in or out. Use Finished embroidery width below to change the actual embroidery size.</p><label class="field mt-sm"><span>Logo for embroidery</span><input id="embroidery-upload" type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg"></label><p class="field-hint" id="embroidery-file-status" role="status"></p><label class="field mt-sm"><span>Finished embroidery width</span><input id="embroidery-width" type="range" min="0.5" step="0.05"><strong id="embroidery-position"></strong></label><div class="fields mt-sm"><label class="field"><span>Move horizontally</span><input id="embroidery-offset-x" type="range" step="0.05"></label><label class="field"><span>Move vertically</span><input id="embroidery-offset-y" type="range" step="0.05"></label></div><div class="field mt-sm"><span>Approximate thread colors</span><div id="embroidery-threads" class="embroidery-threads"></div></div><div id="embroidery-text-block" class="embroidery-extra mt-sm" hidden><label class="check"><input id="embroidery-text-enabled" type="checkbox"><span>Add name/title text on the other chest side (+$7 per line per garment)</span></label><p class="field-hint" id="embroidery-text-side"></p><div class="fields mt-sm"><label class="field"><span>Text line 1 — +$7 each</span><input id="embroidery-text-line1" type="text" maxlength="40" placeholder="Name"></label><label class="field"><span>Text line 2 optional — +$7 each</span><input id="embroidery-text-line2" type="text" maxlength="40" placeholder="Title"></label></div><label class="field mt-sm"><span>Text embroidery width</span><input id="embroidery-text-width" type="range" min="0.75" step="0.05"><strong id="embroidery-text-size"></strong></label><label class="embroidery-thread mt-sm"><span>Text thread</span><input id="embroidery-text-color" type="color"></label></div><p class="field-hint mt-sm">Garment style and thread colors are approximate. We will review your original logo and text and send a proof before production.</p></section>`);
    const [saved]=await Promise.all([getDesign(idFor(p.id)),loadPhoto(p.config.apparel_kind)]);
    if(currentId!==p.id || !$('#embroidery-canvas'))return;
    draft=saved||{id:idFor(p.id),kind:'embroidery-preview',product_id:p.id,original:null,design:defaultDesign(p)};
    try {image=draft.original?await imageFrom(draft.original):null;} catch {image=null;draft.original=null;toast('Saved logo could not be opened. Upload it again.',true);}
    const selected=[...f.querySelectorAll('input[name="print_locations"]')].find(input=>input.value===draft.design.placement);
    if(selected)selected.checked=true;
    sync(p);
    onChange();
    const sourceCanvas=$('#embroidery-canvas'),zoomWindow=$('#embroidery-zoom-window'),zoomCanvas=$('#embroidery-zoom-canvas'),zoomLabel=$('#embroidery-zoom-level');
    let zoomLevel=2.25,zoomClientX=null,zoomClientY=null;
    const drawZoom=()=>{
      if(!sourceCanvas||!zoomCanvas||!zoomWindow?.classList.contains('active'))return;
      const sourceRect=sourceCanvas.getBoundingClientRect(),zoomRect=zoomCanvas.getBoundingClientRect();
      if(!sourceRect.width||!sourceRect.height||!zoomRect.width||!zoomRect.height)return;
      const localX=zoomClientX===null?sourceRect.width/2:clamp(zoomClientX-sourceRect.left,0,sourceRect.width);
      const localY=zoomClientY===null?sourceRect.height/2:clamp(zoomClientY-sourceRect.top,0,sourceRect.height);
      const centerX=localX/sourceRect.width*sourceCanvas.width,centerY=localY/sourceRect.height*sourceCanvas.height;
      const sourceWidth=Math.min(sourceCanvas.width,zoomRect.width*(sourceCanvas.width/sourceRect.width)/zoomLevel);
      const sourceHeight=Math.min(sourceCanvas.height,zoomRect.height*(sourceCanvas.height/sourceRect.height)/zoomLevel);
      const sx=clamp(centerX-sourceWidth/2,0,Math.max(0,sourceCanvas.width-sourceWidth));
      const sy=clamp(centerY-sourceHeight/2,0,Math.max(0,sourceCanvas.height-sourceHeight));
      const z=zoomCanvas.getContext('2d');z.clearRect(0,0,zoomCanvas.width,zoomCanvas.height);z.imageSmoothingEnabled=true;z.imageSmoothingQuality='high';
      z.drawImage(sourceCanvas,sx,sy,sourceWidth,sourceHeight,0,0,zoomCanvas.width,zoomCanvas.height);
      if(zoomLabel)zoomLabel.textContent=`${zoomLevel.toFixed(1)}×`;
    };
    const showZoom=event=>{
      if(!sourceCanvas||!zoomWindow||!zoomCanvas)return;
      if(event&&Number.isFinite(event.clientX)){zoomClientX=event.clientX;zoomClientY=event.clientY;}
      zoomWindow.classList.add('active');zoomWindow.setAttribute('aria-hidden','false');drawZoom();
    };
    const hideZoom=()=>{if(zoomWindow){zoomWindow.classList.remove('active');zoomWindow.setAttribute('aria-hidden','true');}};
    preview.onpointerenter=showZoom;
    preview.onpointermove=event=>{zoomClientX=event.clientX;zoomClientY=event.clientY;showZoom(event);};
    preview.onpointerleave=hideZoom;
    preview.onwheel=event=>{
      event.preventDefault();event.stopPropagation();
      zoomClientX=event.clientX;zoomClientY=event.clientY;
      const step=event.deltaY<0?1.18:1/1.18;
      zoomLevel=clamp(zoomLevel*step,1.25,6);
      showZoom(event);
    };
    zoomRefresh=drawZoom;
    $('#embroidery-upload').onchange=async event=>{
      try {
        const file=event.target.files[0];if(!file)return;fileCheck(file);
        const decoded=await imageFrom(file);
        const limits=embroideryLimits(p,draft.design.placement),ratio=artworkAspectRatio(decoded);
        if(Math.min(limits.width,limits.height*ratio)<Math.max(.5,.2*ratio)) throw new Error('This logo is too narrow or wide for the selected embroidery area.');
        image=decoded;draft.original=file;
        draft.design.thread_colors=dominantColors(decoded);
        await saveDesign(draft);sync(p);onChange();
        window.TampaAnalytics?.track('upload_file');
      } catch(error){toast(error.message,true);} finally {event.target.value='';}
    };
    $('#embroidery-width').oninput=e=>{draft.design.width=Number(e.target.value);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));};
    $('#embroidery-text-enabled').onchange=e=>{draft.design.text.enabled=e.target.checked;sync(p);saveDesign(draft).catch(error=>toast(error.message,true));onChange();};
    for(const field of ['line1','line2'])$(`#embroidery-text-${field}`).oninput=e=>{draft.design.text[field]=e.target.value;draft.design.text.enabled=!!(draft.design.text.line1||draft.design.text.line2);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));onChange();};
    $('#embroidery-text-width').oninput=e=>{draft.design.text.width=Number(e.target.value);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));onChange();};
    $('#embroidery-text-color').oninput=e=>{draft.design.text.thread_color=e.target.value;sync(p);saveDesign(draft).catch(error=>toast(error.message,true));onChange();};
    for(const axis of ['x','y'])$(`#embroidery-offset-${axis}`).oninput=e=>{draft.design[`offset_${axis}`]=Number(e.target.value);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));};
    f.addEventListener('change',event=>{
      if(!$('#embroidery-canvas')||currentId!==p.id)return;
      if(event.target.name==='print_locations'){draft.design.placement=event.target.value;draft.design.offset_x=0;draft.design.offset_y=0;normalizeText(p);saveDesign(draft).catch(error=>toast(error.message,true));}
      if(event.target.dataset.thread!==undefined){draft.design.thread_colors[Number(event.target.dataset.thread)]=event.target.value;saveDesign(draft).catch(error=>toast(error.message,true));}
      sync(p);onChange();
    });
  }
  const selection=()=>draft?.original && draft.product_id===currentId && draft.design.width>=.5 && draft.design.height>=.2 ? structuredClone(draft.design):null;
  async function prepareItems(items) {
    for(const item of items){
      if(!embroidered(product(item.product_id)))continue;
      if(!draft?.original || currentId!==item.product_id)throw new Error('Upload your logo to create an embroidery preview before adding this garment.');
      const id=crypto.randomUUID();await saveDesign({...draft,id,design:structuredClone(draft.design)});
      item.embroidery_id=id;item.embroidery_preview=structuredClone(draft.design);
    }
    return items;
  }
  async function filesFor(items) {
    const files=[];
    for(let index=0;index<items.length;index++){
      const item=items[index],p=product(item.product_id);if(!embroidered(p))continue;
      if(!item.embroidery_id || !item.embroidery_preview)throw new Error(`The logo preview for item ${index+1} is missing. Remove and add that garment again.`);
      const record=await getDesign(item.embroidery_id);
      if(!record?.original)throw new Error(`The original embroidery logo for item ${index+1} is missing. Remove and add that garment again.`);
      fileCheck(record.original);
      const image=await imageFrom(record.original),canvas=document.createElement('canvas');canvas.width=1000;canvas.height=950;
      const selectedColor=p.config.shirt_colors[item.shirt_color]||'#ffffff';
      await renderEmbroidery(canvas,p,image,item.embroidery_preview,selectedColor,true);
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
      if(!blob)throw new Error('Unable to save the embroidery preview. Please try again.');
      const suffix=/\.png$/i.test(record.original.name)?'png':'jpg';
      files.push(new File([record.original],`item-${index+1}-original-embroidery-logo.${suffix}`,{type:record.original.type}));
      files.push(new File([blob],`item-${index+1}-digital-embroidery-preview.png`,{type:'image/png'}));
    }
    return files;
  }
  async function show(item) {
    const p=product(item.product_id),record=await getDesign(item.embroidery_id);
    if(!record?.original)throw new Error('The saved embroidery preview is missing. Remove and add this item again.');
    const image=await imageFrom(record.original),canvas=$('#embroidery-modal-canvas');
    if(canvas)await renderEmbroidery(canvas,p,image,item.embroidery_preview,p.config.shirt_colors[item.shirt_color]||'#ffffff');
  }
  return {setup,selection,prepareItems,filesFor,show};
}
