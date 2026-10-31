(() => {
  const origin = new URL(document.baseURI).origin;
  window.addEventListener('error',e=>console.error('Lone Star runtime:',e.message));
  document.body.style.visibility='hidden';
  let started = false;
  const requests = new Map();
  const safe = value => typeof value === 'string' && (/^https:\/\//i.test(value) || /^\/website-studio\/assets\/[\w.-]+$/.test(value));
  function imageUrl(url, base) {
    if (typeof url === 'string' && /^\/public\/media-library\/[\w.-]+$/.test(url)) return base + url;
    return safe(url) ? url : '/website-studio/assets/vehicle-photo-pending.svg';
  }
  window.addEventListener('message', async event => {
    if (event.source !== parent || event.origin !== origin || event.data?.channel !== 'nxt-lone-star-review') return;
    const message = event.data;
    if (message.result && requests.has(message.requestId)) { requests.get(message.requestId)(message.result); requests.delete(message.requestId); }
    if (started || !Array.isArray(message.inventory)) return;
    started = true;
    window.NXT_CONNECTED = true;
    window.NXT_PUBLIC = message.public === true;
    window.NXT_BOOT_CONFIG = message.config;
    window.NXT_API_BASE = message.apiBase;
    window.NXT_BOOT_INVENTORY = message.inventory.map((v,index) => ({
      id:index+1,canonicalId:String(v.id),name:[v.year,v.make,v.model,v.trim].filter(Boolean).join(' '),
      price:Number(v.price)||0,miles:Number(v.mileage)||0,type:v.body_type||'',stock:v.stock||'',vin:v.vin||'',
      fuel:v.fuel||'',drive:v.drive||'',trim:v.trim||'',engine:'Confirm with dealer',transmission:v.transmission||'',
      exterior:v.exterior||'',interior:v.interior||'',seats:'',doors:'',features:[],badge:v.badge||'',description:'Contact our team for vehicle condition and equipment details.',
      location_id:v.location_id,location_name:v.location_name,location_address:v.location_address,
      photos:(v.photos?.length?v.photos:[v.image_url]).filter(Boolean).map(url=>imageUrl(url,message.apiBase)),video:'',historyUrl:''
    }));
    window.INVENTORY=window.NXT_BOOT_INVENTORY;
    const grid=document.querySelector('.inventorygrid');
    for(const car of window.NXT_BOOT_INVENTORY){
      if(!car.photos.length)car.photos=['/website-studio/assets/vehicle-photo-pending.svg'];
      car.photo=car.photos[0];
      const card=document.createElement('article');card.className='vehicle';card.dataset.vehicle=car.id;
      // Static markup only. All inventory values enter textContent or safe image src.
      card.innerHTML='<div class="vehiclephoto"><img loading="lazy"><span></span></div><div class="vehiclebody"><h3></h3><p></p><div class="vehiclebottom"><b class="price"></b><button>View details ↗</button></div></div><div class="vehicletools"><button class="compare-toggle" aria-pressed="false">＋ Compare / save</button><span></span></div>';
      card.querySelector('.vehiclephoto span').textContent=car.badge;
      card.querySelector('.vehiclephoto span').dataset.inventoryBadge=car.badge;
      card.querySelector('.vehiclephoto span').setAttribute('data-no-translate','');
      card.querySelector('.vehiclephoto span').hidden=!car.badge;
      card.querySelector('img').decoding='async';
      card.querySelector('img').width=960;card.querySelector('img').height=640;
      card.querySelector('img').src=car.photo;card.querySelector('img').alt=car.name;
      card.querySelector('h3').textContent=car.name;card.querySelector('p').textContent=car.miles.toLocaleString()+' miles · '+car.drive;
      card.querySelector('.price').textContent=car.price?'$'+car.price.toLocaleString():'Contact for price';
      card.querySelector('.vehiclebottom button').dataset.details=car.id;
      card.querySelector('.compare-toggle').dataset.compare=car.id;
      card.querySelector('.vehicletools span').textContent=car.photos.length+' photos';grid.append(card);
    }
    const translateBadges=()=>document.querySelectorAll('[data-inventory-badge]').forEach(el=>{
      const label=el.dataset.inventoryBadge;
      el.textContent=document.documentElement.lang==='es'?({'Featured':'Destacado','Just added':'Recien agregado'}[label]||label):label;
    });
    document.addEventListener('nxtdeal:language',translateBadges);
    translateBadges();
    window.NXT_CONNECTED_SEND=async(form,kind,vehicles,extra={})=>{
      const status=form.querySelector('.statusmessage'),button=form.querySelector('[type=submit]');
      if(!window.NXT_PUBLIC){status.textContent='Preview only. Open the approved public website to send an inquiry.';return;}
      if(!form.reportValidity())return;
      const fields=Object.fromEntries(new FormData(form));
      if(fields.intent==='test-drive')fields.intent='test_drive';
      const payload={name:fields.name,email:fields.email,phone:fields.phone,vehicle_id:vehicles[0]?.canonicalId,
        intent:['information','purchase','test_drive','financing','trade'].includes(fields.intent)?fields.intent:kind==='Sales Free request'?'purchase':'information',
        message:[kind,fields.message||'',...Object.entries(fields).filter(([k])=>!['name','email','phone','message'].includes(k)).map(([k,v])=>k+': '+v),...vehicles.map(v=>'Vehicle: '+v.name+' ['+v.canonicalId+']'),JSON.stringify(extra)].join('\n')};
      const key=JSON.stringify(payload);if(form.dataset.requestPayload!==key){form.dataset.requestPayload=key;form.dataset.requestId=crypto.randomUUID();}
      const requestId=form.dataset.requestId;button.disabled=true;status.textContent='Sending your request…';
      try{
        const result=await new Promise(resolve=>{const timer=setTimeout(()=>{requests.delete(requestId);resolve({error:'No confirmation received. Please retry; your request will not be duplicated.'});},20000);requests.set(requestId,value=>{clearTimeout(timer);resolve(value);});parent.postMessage({channel:'nxt-lone-star-review',requestId,inquiry:{...payload,request_id:requestId}},origin);});
        if(result.error)throw Error(result.error);
        status.textContent=document.documentElement.lang==='es'?'Recibimos tu solicitud. El equipo se comunicará contigo.':'Your request was received. Our team will follow up.';
        form.reset();delete form.dataset.requestPayload;delete form.dataset.requestId;
      }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
    };
    for(const old of [...document.querySelectorAll('script[type="text/nxt-deferred"]')]){
      const script=document.createElement('script');
      if(old.src){script.src=old.src;await new Promise((resolve,reject)=>{script.onload=resolve;script.onerror=reject;old.replaceWith(script);});}
      else{script.textContent=old.textContent;old.replaceWith(script);}
    }
    // Service requests use the canonical dealer inquiry workflow; staff confirm booking.
    const appointment=document.querySelector('#appointmentForm');
    if(appointment){
      const serviceLabel=()=>{appointment.querySelector('[type=submit]').textContent=document.documentElement.lang==='es'?'Solicitar cita':'Request appointment';};
      serviceLabel();document.addEventListener('nxtdeal:language',serviceLabel);
      appointment.onsubmit=async event=>{
        event.preventDefault();
        const date=appointment.elements.namedItem('date').value;
        const now=new Date(),today=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
        if(date<today){appointment.querySelector('.statusmessage').textContent='Choose today or a future date.';return;}
        await window.NXT_CONNECTED_SEND(appointment,'Service appointment request (dealer confirmation required)',[]);
      };
    }
    document.body.style.visibility='visible';
    if(window.NXT_PUBLIC){
      document.querySelectorAll("#chatLauncher,#dealerChat").forEach(el=>el.remove());
      let last='';
      document.addEventListener('click',event=>{
        const link=event.target.closest('a[href^="#"]');
        if(!link)return;
        const page=link.getAttribute('href').slice(1);
        if(page===last)return;last=page;
        parent.postMessage({channel:'nxt-lone-star-review',activity:{event:'section_view',page}},origin);
      });
    }

    // The connected stock never falls back to the original six demo cars.
    document.querySelector('.results').textContent=window.INVENTORY.length+' vehicles available';
    const note=document.querySelector('#generalContactForm .formnote');if(note)note.textContent='Your request is sent to our dealership team.';
    document.querySelectorAll('form p,form small').forEach(p=>{if(p.textContent.startsWith('Preview only:')){p.setAttribute('data-no-translate','');p.textContent=window.NXT_PUBLIC?'Your request is sent to our dealership team.':'Preview only. Inquiries are disabled here.';}});
  });
  parent.postMessage({channel:'nxt-lone-star-review',ready:true},origin);
})();
