// A visual embroidery approximation. Original artwork is always kept for shop digitizing.
const MAX_BYTES = 50 * 1024 * 1024;
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
export const embroidered = product => product?.config?.apparel_kind?.startsWith('embroidered_');
export const embroideryLimits = (product, placement) => {
  const option = product.config.placement_options.find(p => p.id === placement);
  if (!option) throw new Error('Choose a valid embroidery placement.');
  return {width: Number(option.width), height: Number(option.height), offset: placement === 'front' ? .35 : .75};
};

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
const shade = (hex, amount) => '#' + toRgb(hex).map(value =>
  clamp(Math.round(amount >= 0 ? value + (255-value)*amount : value*(1+amount)),0,255)
    .toString(16).padStart(2,'0')).join('');
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
    const shine=Math.sin((px+py*.6)*2.1)*12 + Math.sin(py*.75)*5;
    for (let j=0;j<3;j++) pixels[i+j]=clamp(nearest[j]+shine,0,255);
  }
  c.putImageData(frame,0,0);
  context.save();context.shadowColor='rgba(5,12,20,.52)';context.shadowBlur=5;context.shadowOffsetY=3;
  context.drawImage(canvas,x,y);context.restore();
  // Short diagonal highlights are clipped to the logo's nontransparent pixels.
  const sheen=document.createElement('canvas');sheen.width=canvas.width;sheen.height=canvas.height;
  const s=sheen.getContext('2d');s.strokeStyle='rgba(255,255,255,.25)';s.lineWidth=1;
  for(let row=-canvas.width;row<canvas.height+canvas.width;row+=4){
    s.beginPath();s.moveTo(0,row);s.lineTo(canvas.width,row-canvas.width*.35);s.stroke();
  }
  s.globalCompositeOperation='destination-in';s.drawImage(canvas,0,0);
  context.drawImage(sheen,x,y);
}

function garment(context, kind, color, placement) {
  const c=context, gradient=c.createLinearGradient(160,130,630,640);
  gradient.addColorStop(0,shade(color,.14));gradient.addColorStop(.42,color);gradient.addColorStop(1,shade(color,-.2));
  c.lineJoin='round';c.lineCap='round';c.shadowColor='#15233045';c.shadowBlur=25;c.shadowOffsetY=14;
  if(kind==='embroidered_hat') {
    c.fillStyle=gradient;c.strokeStyle='#15222c66';c.lineWidth=3;
    c.beginPath();c.moveTo(205,395);c.bezierCurveTo(205,220,289,174,400,174);c.bezierCurveTo(523,174,596,241,595,395);c.quadraticCurveTo(400,479,205,395);c.fill();c.stroke();
    c.shadowBlur=13;c.beginPath();c.moveTo(215,409);c.quadraticCurveTo(400,439,585,409);c.quadraticCurveTo(682,452,636,479);c.quadraticCurveTo(400,526,163,479);c.quadraticCurveTo(120,451,215,409);c.fill();c.stroke();
    c.shadowColor='transparent';c.strokeStyle='#ffffff66';c.lineWidth=2;
    c.beginPath();c.moveTo(400,179);c.lineTo(400,236);c.moveTo(205,387);c.quadraticCurveTo(400,417,595,387);c.stroke();
    c.fillStyle=color;c.beginPath();c.arc(400,172,10,0,Math.PI*2);c.fill();
  } else {
    c.fillStyle=gradient;c.strokeStyle='#10263570';c.lineWidth=2.5;
    c.beginPath();c.moveTo(267,142);c.lineTo(183,161);c.lineTo(98,290);c.lineTo(179,339);c.lineTo(236,275);c.lineTo(235,596);
    c.quadraticCurveTo(400,626,565,596);c.lineTo(564,275);c.lineTo(621,339);c.lineTo(702,290);c.lineTo(617,161);c.lineTo(533,142);
    c.quadraticCurveTo(467,190,400,190);c.quadraticCurveTo(333,190,267,142);c.closePath();c.fill();c.stroke();
    c.shadowColor='transparent';c.strokeStyle='#ffffff54';c.lineWidth=2;
    c.beginPath();c.moveTo(234,290);c.lineTo(235,584);c.moveTo(566,290);c.lineTo(565,584);c.moveTo(190,165);c.quadraticCurveTo(209,222,186,317);c.moveTo(610,165);c.quadraticCurveTo(591,222,614,317);c.stroke();
    if(kind==='embroidered_hoodie') {
      c.fillStyle=color;c.strokeStyle='#17263588';c.lineWidth=3;c.beginPath();
      c.moveTo(267,142);c.quadraticCurveTo(286,74,342,73);c.quadraticCurveTo(400,104,458,73);c.quadraticCurveTo(514,75,533,142);
      c.quadraticCurveTo(471,214,400,231);c.quadraticCurveTo(329,214,267,142);c.fill();c.stroke();
      c.strokeStyle='#ffffff9a';c.beginPath();c.moveTo(381,206);c.lineTo(373,273);c.moveTo(419,206);c.lineTo(427,273);c.stroke();
      c.strokeStyle='#0b20344a';c.beginPath();c.moveTo(322,440);c.quadraticCurveTo(400,456,478,440);c.lineTo(497,534);c.quadraticCurveTo(400,550,303,534);c.closePath();c.stroke();
    } else if(kind==='embroidered_jacket') {
      c.strokeStyle='#ffffff9a';c.lineWidth=3;c.beginPath();c.moveTo(400,194);c.lineTo(400,605);c.stroke();
      c.strokeStyle='#1227378c';c.beginPath();c.moveTo(267,142);c.lineTo(330,241);c.lineTo(400,196);c.lineTo(470,241);c.lineTo(533,142);c.stroke();
      c.beginPath();c.moveTo(268,437);c.lineTo(348,437);c.moveTo(452,437);c.lineTo(532,437);c.stroke();
    } else if(kind==='embroidered_polo') {
      c.fillStyle=color;c.strokeStyle='#142a3b88';c.lineWidth=2;c.beginPath();c.moveTo(267,142);c.lineTo(320,219);c.lineTo(380,191);c.lineTo(400,272);c.lineTo(420,191);c.lineTo(480,219);c.lineTo(533,142);c.quadraticCurveTo(467,191,400,190);c.quadraticCurveTo(333,191,267,142);c.fill();c.stroke();
      c.fillStyle='#ffffff91';for(const yy of [226,245,264]){c.beginPath();c.arc(400,yy,2.2,0,Math.PI*2);c.fill();}
    } else {
      c.strokeStyle='#10263566';c.beginPath();c.arc(400,142,54,.08,Math.PI-.08);c.stroke();
    }
  }
  c.shadowColor='transparent';
}

export function renderEmbroidery(canvas, product, fileImage, design, color, caption=false) {
  const c=canvas.getContext('2d'), sx=canvas.width/800, sy=canvas.height/(caption?760:680);
  c.save();c.scale(sx,sy);
  const background=c.createLinearGradient(0,0,0,680);background.addColorStop(0,'#edf3f5');background.addColorStop(1,'#dce6e9');
  c.fillStyle=background;c.fillRect(0,0,800,caption?760:680);
  c.fillStyle='#536b78';c.font='600 15px Arial, sans-serif';c.fillText('TAMPA SIGNS  /  EMBROIDERY PREVIEW',34,43);
  garment(c,product.config.apparel_kind,color,design.placement);
  const hat=product.config.apparel_kind==='embroidered_hat';
  const centerX=hat?400:design.placement==='right_chest'?319:481, centerY=hat?316:322;
  const ppi=hat?49:29;
  const width=design.width*ppi, height=design.height*ppi;
  const x=centerX+design.offset_x*ppi-width/2, y=centerY+design.offset_y*ppi-height/2;
  if(fileImage && design.thread_colors?.length) drawThread(c,fileImage,width,height,design.thread_colors,x,y);
  else {
    c.setLineDash([7,6]);c.strokeStyle='#eef4ffb8';c.lineWidth=2;c.strokeRect(x,y,width,height);c.setLineDash([]);
    c.fillStyle='#eef4ffe8';c.font='600 15px Arial, sans-serif';c.textAlign='center';c.fillText('YOUR LOGO',centerX,centerY);c.textAlign='left';
  }
  c.fillStyle='#293f4b';c.font='600 14px Arial, sans-serif';
  c.fillText(`${design.width.toFixed(2)} × ${design.height.toFixed(2)} in  ·  ${design.placement.replace('_',' ')}`,34,650);
  if(caption){
    c.fillStyle='#ffffff';c.fillRect(0,680,800,80);c.fillStyle='#293f4b';c.font='15px Arial, sans-serif';
    c.fillText('Digital representation only. Thread colors, stitch direction, details and size may vary.',26,712);
    c.fillText('Original artwork must be digitized and approved by Tampa Signs before production.',26,740);
  }
  c.restore();
}

const imageFrom = async file => {
  const url=URL.createObjectURL(file), image=new Image();
  try {
    image.src=url;await image.decode();
    if (!image.width || image.width*image.height>50_000_000) throw new Error('The logo is empty or exceeds 50 megapixels.');
    const canvas=document.createElement('canvas'),scale=Math.min(1,640/Math.max(image.width,image.height));
    canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));
    canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
    return canvas;
  } finally {URL.revokeObjectURL(url);}
};

export function createEmbroidery(ctx) {
  const {getDesign,saveDesign,product,esc,toast,onChange}=ctx;
  const idFor=id=>`embroidery-draft-${id}`;
  let draft=null, image=null, currentId=null;
  const $=selector=>document.querySelector(selector);
  const fileCheck=file=>{
    if(!file || !/\.(png|jpe?g)$/i.test(file.name) || !['image/png','image/jpeg'].includes(file.type)) throw new Error('Choose a PNG or JPG logo for the live preview. You may attach a PDF separately to your project.');
    if(!file.size || file.size>MAX_BYTES) throw new Error('Logo files must be nonempty and at most 50 MB.');
  };
  function defaultDesign(p) {
    return {placement:p.config.placement_options[0].id,width:p.config.apparel_kind==='embroidered_hat'?3.25:3.5,
      height:p.config.apparel_kind==='embroidered_hat'?1.65:3.5,offset_x:0,offset_y:0,thread_colors:['#ffffff']};
  }
  const colorFor=p=>p.config.shirt_colors[$('#calculator')?.elements.shirt_color?.value]||'#ffffff';
  function sync(p) {
    if(!draft)return;
    const max=embroideryLimits(p,draft.design.placement);
    const ratio=image ? image.width/image.height : 1;
    if(Math.min(max.width,max.height*ratio)<Math.max(.5,.2*ratio)){
      throw new Error('This logo is too narrow or wide for the selected embroidery area. Upload a cropped version with less empty space.');
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
    const canvas=$('#embroidery-canvas');if(canvas)renderEmbroidery(canvas,p,image,draft.design,colorFor(p));
    const status=$('#embroidery-file-status');if(status)status.textContent=draft.original?`${draft.original.name} saved for your project`:'Upload a logo to see the stitched preview.';
  }
  async function setup(p) {
    if(!embroidered(p))return;
    currentId=p.id;draft=null;image=null;const f=$('#calculator');
    const preview=$('.product-preview');preview.classList.add('embroidery-product-preview');
    preview.innerHTML='<canvas id="embroidery-canvas" width="800" height="680" aria-label="Digital embroidery mockup on the selected garment"></canvas>';
    f.insertAdjacentHTML('beforeend',`<section class="embroidery-controls"><h3>Preview your embroidery</h3><p class="field-hint">Upload a PNG or JPG logo (up to 50 MB). A transparent PNG gives the clearest stitch preview.</p><label class="field mt-sm"><span>Logo for embroidery</span><input id="embroidery-upload" type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg"></label><p class="field-hint" id="embroidery-file-status" role="status"></p><label class="field mt-sm"><span>Finished embroidery width</span><input id="embroidery-width" type="range" min="0.5" step="0.05"><strong id="embroidery-position"></strong></label><div class="fields mt-sm"><label class="field"><span>Move horizontally</span><input id="embroidery-offset-x" type="range" step="0.05"></label><label class="field"><span>Move vertically</span><input id="embroidery-offset-y" type="range" step="0.05"></label></div><div class="field mt-sm"><span>Approximate thread colors</span><div id="embroidery-threads" class="embroidery-threads"></div></div><p class="field-hint mt-sm">Digital representation only. Thread colors, stitch direction, fine details and final sizing may vary during digitizing and production. The shop will review your original artwork and provide a proof.</p></section>`);
    const saved=await getDesign(idFor(p.id));
    if(currentId!==p.id || !$('#embroidery-canvas'))return;
    draft=saved||{id:idFor(p.id),kind:'embroidery-preview',product_id:p.id,original:null,design:defaultDesign(p)};
    try {image=draft.original?await imageFrom(draft.original):null;} catch {image=null;draft.original=null;toast('Saved logo could not be opened. Upload it again.',true);}
    const selected=[...f.querySelectorAll('input[name="print_locations"]')].find(input=>input.value===draft.design.placement);
    if(selected)selected.checked=true;
    sync(p);
    onChange();
    $('#embroidery-upload').onchange=async event=>{
      try {
        const file=event.target.files[0];if(!file)return;fileCheck(file);
        const decoded=await imageFrom(file);
        const limits=embroideryLimits(p,draft.design.placement),ratio=decoded.width/decoded.height;
        if(Math.min(limits.width,limits.height*ratio)<Math.max(.5,.2*ratio)) throw new Error('This logo is too narrow or wide for the embroidery area. Crop excess blank space and upload it again.');
        image=decoded;draft.original=file;
        draft.design.thread_colors=dominantColors(decoded);
        await saveDesign(draft);sync(p);onChange();
        window.TampaAnalytics?.track('upload_file');
      } catch(error){toast(error.message,true);} finally {event.target.value='';}
    };
    $('#embroidery-width').oninput=e=>{draft.design.width=Number(e.target.value);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));};
    for(const axis of ['x','y'])$(`#embroidery-offset-${axis}`).oninput=e=>{draft.design[`offset_${axis}`]=Number(e.target.value);sync(p);saveDesign(draft).catch(error=>toast(error.message,true));};
    f.addEventListener('change',event=>{
      if(!$('#embroidery-canvas')||currentId!==p.id)return;
      if(event.target.name==='print_locations'){draft.design.placement=event.target.value;draft.design.offset_x=0;draft.design.offset_y=0;saveDesign(draft).catch(error=>toast(error.message,true));}
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
      renderEmbroidery(canvas,p,image,item.embroidery_preview,selectedColor,true);
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
    if(canvas)renderEmbroidery(canvas,p,image,item.embroidery_preview,p.config.shirt_colors[item.shirt_color]||'#ffffff');
  }
  return {setup,selection,prepareItems,filesFor,show};
}
