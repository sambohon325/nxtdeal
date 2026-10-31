(() => {
  const origin = new URL(document.baseURI).origin;
  const setText = (selector, value) => { const node = document.querySelector(selector); if (node && typeof value === 'string') { node.setAttribute('data-no-translate', ''); node.textContent = value; } };
  const safeImage = value => typeof value === 'string' && (/^https?:\/\//.test(value) || /^\/website-studio\/assets\/[a-zA-Z0-9_.-]+$/.test(value) || /^data:image\/(png|jpeg|webp);base64,[a-zA-Z0-9+/=]+$/.test(value));
  const defaults = window.NXT_TEMPLATE_DEFAULTS;
  const originals = new Map();
  const updateCopy = (key, selector, value) => {
    const node=document.querySelector(selector);if(!node || typeof value!=='string')return;
    if(!originals.has(key)) originals.set(key,node.innerHTML);
    if(defaults && value===defaults[key])node.innerHTML=originals.get(key);
    else setText(selector,value);
  };
  let previousName=defaults?.name || 'Lone Star Auto';
  let latest = window.NXT_BOOT_CONFIG || null;
  const media = url => typeof url === 'string' && /^\/public\/media-library\/[\w.-]+$/.test(url) ? window.NXT_API_BASE + url : url;
  function renderCoupons(config) {
    const service=document.getElementById('service');if(!service)return;
    let grid=service.querySelector('.coupon-grid');if(!grid){grid=document.createElement('div');grid.className='coupon-grid';service.append(grid);}
    grid.replaceChildren();grid.setAttribute('data-no-translate','');
    const es=document.documentElement.lang==='es',today=new Date().toISOString().slice(0,10);
    for(const c of config.coupons||[]){
      if(!c.enabled||(c.start&&today<c.start)||(c.end&&today>c.end))continue;
      const card=document.createElement('article');card.className='coupon';
      for(const [tag,text] of [['h3',es?(c.titleEs||c.title):c.title],['p',es?(c.summaryEs||c.summary):c.summary],['strong',c.code],['p',[c.start,c.end].filter(Boolean).join(' – ')],['p',es?(c.termsEs||c.terms):c.terms]]){if(text){const el=document.createElement(tag);el.textContent=text;card.append(el);}}
      const link=document.createElement('a');link.className='button';link.href='#contact';link.textContent=es?'Consultar cupón ↗':'Ask about this coupon ↗';link.addEventListener('click',event=>{const serviceButton=service.querySelector('[data-service-open]');if(serviceButton){event.preventDefault();serviceButton.click();const field=document.querySelector('#appointmentForm [name=coupon]');if(field)field.value=[c.title,c.code].filter(Boolean).join(' · ');return;}const message=document.querySelector('#generalContactForm textarea');if(message)message.value=[c.title,c.code].filter(Boolean).join(' · ');});card.append(link);grid.append(card);
    }
    grid.hidden=!grid.children.length;
  }
  document.addEventListener('change',event=>{if(event.target.matches('[data-language-select]')&&latest)setTimeout(()=>renderCoupons(latest),0);});
  function apply(config) {
    if (!config) return;
    renderCoupons(config);
    config=JSON.parse(JSON.stringify(config));
    for(const key of ['hero','teamPhoto'])config[key]=media(config[key]);
    for(const key of Object.keys(config.backgrounds||{}))config.backgrounds[key]=media(config.backgrounds[key]);
    if(config.event){config.event.banner=media(config.event.banner);config.event.event=media(config.event.event);}
    if(window.NXT_CONNECTED){
      const locations=new Map((config.locations||[]).map(l=>[l.id,l]));
      for(const v of window.INVENTORY||[]){const id=v.location_id||'unassigned';if(!locations.has(id))locations.set(id,{id,name:v.location_name||'Confirm location',address:v.location_address||'Contact the dealership to confirm this location',phone:'',hours:''});}
      config.locations=[...locations.values()];
    }
    if (config.name) {
      if(defaults){setText('[data-custom-name]',config.name);}else setText('.logo', config.name);
      document.title=config.name;
      const footer=document.querySelector('footer');if(footer){const walker=document.createTreeWalker(footer,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode()){if(/^\s*©/.test(node.textContent)){node.parentElement.setAttribute('data-no-translate','');node.textContent='© '+new Date().getFullYear()+' '+config.name;}else if(node.textContent.includes(previousName))node.textContent=node.textContent.replaceAll(previousName,config.name);}}
      previousName=config.name;
      if (window.DEALER_CONFIG) window.DEALER_CONFIG.dealer = config.name;
      if (window.ASSISTANT_CONFIG) window.ASSISTANT_CONFIG.dealer = config.name;
      setText('#team .sectionhead p', 'Get to know the people and the place behind ' + config.name + '.');
    }
    if (config.headline) updateCopy('headline', defaults?'[data-custom-headline]':'.ls-intro h1', config.headline);
    if (config.intro) updateCopy('intro', defaults?'[data-custom-intro]':'.ls-intro > p', config.intro);
    if (config.story) updateCopy('story', defaults?'[data-custom-story]':'.ls-about-copy > p', config.story);
    const hero=document.querySelector(defaults?'[data-custom-hero]':'.ls-truck > img');if(hero && safeImage(config.hero))hero.src=config.hero;
    const team=document.querySelector(defaults?'[data-custom-team]':'.ls-about-story figure img');if(team && safeImage(config.teamPhoto))team.src=config.teamPhoto;
    if (Array.isArray(config.locations) && config.locations.length && window.NXT_STUDIO_LOCATIONS) window.NXT_STUDIO_LOCATIONS(config.locations);
    if (config.socials && window.NXT_STUDIO_SOCIALS) window.NXT_STUDIO_SOCIALS(config.socials);
    if(window.NXT_PUBLIC){const socials=document.querySelector('[aria-label="Dealership social media"]');if(socials)socials.hidden=!socials.querySelector('a[href]');}
    if (config.backgrounds && window.NXT_STUDIO_BACKGROUND) for (const [key, url] of Object.entries(config.backgrounds)) {
      if (['trade','contact'].includes(key) && (!url || safeImage(url))) window.NXT_STUDIO_BACKGROUND(key, url);
    }
    if (config.event && window.NXT_STUDIO_EVENTS) {
      const template = window.NXT_EVENT_TEMPLATES.find(item => item.id === config.event.template);
      if (template) {
        const offer = { ...window.NXT_STUDIO_EVENTS.starter(template), ...config.event };
        offer.id='lone-star-event'; offer.domId='promotion-0';
        offer.banner = config.event.banner && safeImage(config.event.banner) ? config.event.banner : template.banner;
        offer.event = config.event.event && safeImage(config.event.event) ? config.event.event : template.image;
        window.NXT_STUDIO_EVENTS.apply(offer);
      }
    }
  }
  window.addEventListener('message', event => {
    if (event.source !== parent || event.origin !== origin || event.data?.channel !== 'nxt-lone-star-review') return;
    if (event.data.config) { latest = event.data.config; apply(latest); }
    if (event.data.jump) document.getElementById(event.data.jump)?.scrollIntoView({behavior:'smooth', block:'start'});
    if (event.data.language) { const select=document.querySelector('[data-language-select]'); if(select){select.value=event.data.language;select.dispatchEvent(new Event('change'));} }
  });
  const ready = setInterval(() => {
    if (!window.NXT_STUDIO_EVENTS || !window.NXT_STUDIO_LOCATIONS || !window.NXT_STUDIO_SOCIALS) return;
    clearInterval(ready); apply(latest); parent.postMessage({channel:'nxt-lone-star-review',ready:true}, origin);
  }, 100);
  // Keep the approved shopping/service interactions, but no demo downloads or requests.
  const capture = new Set(['generalContactForm','inquiryForm','orderForm','vehicleLeadForm','appointmentForm','repairForm','quoteForm']);
  document.addEventListener('submit', event => {
    if (!capture.has(event.target.id)) return;
    if(window.NXT_CONNECTED && ['generalContactForm','inquiryForm','orderForm','vehicleLeadForm','appointmentForm'].includes(event.target.id))return;
    event.preventDefault();event.stopImmediatePropagation();
    let notice=event.target.querySelector('.nxt-preview-result');
    if(!notice){notice=document.createElement('p');notice.className='nxt-preview-result';notice.setAttribute('role','status');event.target.append(notice);}
    notice.textContent=document.documentElement.lang==='es'?'Vista previa: no se envió ninguna solicitud.':'Preview only — no request was sent. This form will use NXTDeal’s connected workflow.';
  },true);
  document.addEventListener('click', event => {
    const link=event.target.closest('a');if(!link)return;
    if(link.hasAttribute('download')) {event.preventDefault();event.stopImmediatePropagation();}
    if(!window.NXT_PUBLIC && /^(https?:|tel:|mailto:)/i.test(link.getAttribute('href')||'')){event.preventDefault();event.stopImmediatePropagation();}
  },true);
})();
