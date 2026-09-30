export function belowCheckoutMinimum(quote) {
  return !quote.review_required && quote.meets_minimum_order === false;
}

export function minimumCheckoutMessage(quote) {
  const dollars=cents=>'$'+(cents/100).toFixed(2);
  return `Online checkout requires ${dollars(quote.minimum_order_cents)} before tax and shipping. Add ${dollars(Math.max(0,quote.minimum_order_cents-quote.subtotal_cents))} more in products or increase quantity to continue.`;
}

// Persist the exact approval and rewards before opening payment. Failures retain
// the saved order and stop the payment handoff, so retrying never re-approves it.
export async function submitOrderCheckout({api,setCsrf,buy,quote,payload,review}) {
  if(belowCheckoutMinimum(quote))throw new Error(minimumCheckoutMessage(quote));
  if(payload.confirm!==true)throw new Error('Review and accept the artwork and terms before continuing.');
  const order=await api(buy?'/api/orders':'/api/requests','POST',payload);
  if(order.csrf)setCsrf(order.csrf);
  else{
    const token=new URL(order.portal_url).hash.slice(7);
    const session=await api('/api/portal/exchange','POST',{token});
    setCsrf(session.csrf);
  }
  let problem='',checkout=null,artworkApproved=false,paymentFailed=false;
  const approvedFiles=[];
  for(const item of review.files){
    try{
      const data=new FormData();data.append('file',item.file);
      const uploaded=await api(`/api/jobs/${order.job_id}/artwork`,'POST',data);
      if(item.approved)approvedFiles.push({asset_id:uploaded.asset_id,sha256:uploaded.sha256,line_indices:[...item.line_indices]});
    }catch(error){problem='An artwork upload needs attention: '+error.message;break;}
  }
  if(review.approve&&!problem){
    try{await api('/api/portal/artwork-preview/approve','POST',{
      name:payload.customer_name,confirm:true,terms_version:payload.terms_version,
      quote_version:1,files:approvedFiles});artworkApproved=true;}
    catch(error){problem='Artwork approval needs attention: '+error.message;}
  }
  if(buy&&!problem&&(Number(payload.reward_credit)>0||Number(payload.reward_points)>0)){
    try{await api('/api/portal/rewards/apply','POST',{
      credit:payload.reward_credit||'0',points:Number(payload.reward_points||0),confirm:true,quote_version:1});}
    catch(error){problem='Your rewards selection needs attention: '+error.message;}
  }
  if(buy&&!problem){
    try{checkout=await api('/api/portal/checkout','POST',{});
      if(!checkout.url)throw new Error('The payment link was not returned. Try Continue to secure payment in your order page.');}
    catch(error){paymentFailed=true;problem='Your order is saved, but payment could not open: '+error.message;}
  }
  return {order,problem,checkout,artworkApproved,paymentFailed};
}
