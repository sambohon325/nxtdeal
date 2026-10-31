"""Primary-source capability register with explicit, category-level hypotheses.

Numbers below are analyst planning assumptions, NEVER vendor prices or measured lifts.
Similar capabilities intentionally share priors; this is not a vendor ranking.
"""
import copy

RESEARCH_DATE = '2026-09-14'
CATALOGUE_VERSION = '2026.09.15.2'
EFFECT_LABELS = {
    'capture_lift': 'Unique sales-lead capture (%)', 'response_lift': 'Response rate (%)',
    'appointment_lift': 'Appointment rate (%)', 'show_lift': 'Show rate (%)', 'close_lift': 'Close rate (%)',
    'paid_efficiency_lift': 'Paid leads per advertising dollar (%)', 'lead_capacity_lift': 'Lead-handling capacity (%)',
    'sales_capacity_lift': 'Sales delivery capacity (%)', 'gross_lift': 'Vehicle gross per sale (%)',
    'fi_lift': 'F&I gross per sale (%)', 'service_demand_lift': 'Service demand (%)',
    'service_capacity_lift': 'Service capacity (%)', 'service_value_lift': 'Service gross per RO (%)',
    'holding_reduction': 'Inventory carrying-cost reduction (%)', 'admin_hours_saved': 'Admin hours released per month',
}
OPERATING_DEFAULTS = {'service_requests': 0, 'service_capacity': 0, 'service_gross_per_ro': 0, 'fi_gross_per_sale': 0, 'holding_cost_per_vehicle': 0, 'admin_hours': 0}

def prior(category, monthly, setup, ramp, effects, reasoning, limitations):
    return {'category': category, 'monthly_range': monthly, 'setup_range': setup, 'ramp_months': ramp, 'adoption': 75,
            'effects': effects, 'reasoning': reasoning, 'limitations': limitations}

PRIORS = {
 'crm': prior('CRM', [1000,2000,4000], [500,2000,6000], 3, {'response_lift':5,'appointment_lift':3,'lead_capacity_lift':5,'admin_hours_saved':12}, 'Centralized conversations and follow-up may reduce missed contacts and duplicate entry.', 'Existing CRM performance may already be in your baseline. Compare replacements, not two full CRMs added together.'),
 'dms': prior('DMS & operations', [3000,6000,12000], [5000,15000,40000], 6, {'sales_capacity_lift':3,'service_capacity_lift':3,'admin_hours_saved':40}, 'Connected transaction and service workflows may increase usable capacity and reduce administration.', 'Migration, training, data access and integrations can dominate outcomes. No automatic sales-demand lift or monetized payroll saving.'),
 'website': prior('Websites', [700,1500,3000], [500,2000,6000], 3, {'capture_lift':4,'admin_hours_saved':8}, 'Search, merchandising and forms may convert a small additional share of existing shoppers into unique leads.', 'Assumes a meaningful improvement over the current website. No automatic traffic growth or bundled paid media.'),
 'digital': prior('Digital retailing', [700,1400,3000], [500,2000,5000], 3, {'close_lift':3,'sales_capacity_lift':4,'admin_hours_saved':8}, 'Payment exploration and connected deal steps may reduce abandonment and re-keying.', 'No improved credit approval assumption. Lender access and accurate payment integration must be verified.'),
 'retention': prior('Retention & data activation', [1000,2200,4500], [500,2000,6000], 4, {'capture_lift':4,'service_demand_lift':3,'admin_hours_saved':10}, 'Reactivation and timely customer outreach may create incremental sales and service opportunities.', 'The model uses aggregate incremental demand, not lifetime value or individual customer cohorts. Mailing and media budgets are separate.'),
 'ads': prior('Advertising', [500,1200,2500], [0,750,2500], 2, {'paid_efficiency_lift':6,'admin_hours_saved':10}, 'Inventory-based creative and audience selection may produce more unique paid leads at the same spend.', 'Fees exclude media. Do not include management fees again in advertising spend. This is not guaranteed CPL improvement.'),
 'ai': prior('Conversational AI & BDC', [600,1500,3500], [0,1000,4000], 2, {'capture_lift':3,'response_lift':6,'appointment_lift':3,'lead_capacity_lift':8}, 'After-hours coverage and follow-up may capture missed inquiries and free lead-handling capacity.', 'Quality, escalation and CRM integration matter. No assumption of autonomous closed sales or staff elimination.'),
 'inventory': prior('Inventory & pricing', [700,1500,3000], [0,1000,3000], 3, {'gross_lift':1,'holding_reduction':4,'admin_hours_saved':8}, 'Pricing and appraisal guidance may protect gross and reduce avoidable carrying expense.', 'Does not create inventory or model auction prices, individual stock aging or trade-in acquisition. Gross is a blended proxy.'),
 'recon': prior('Reconditioning', [300,700,1600], [0,500,2000], 2, {'holding_reduction':6,'admin_hours_saved':8}, 'Recon workflow visibility may reduce the avoidable component of carrying costs.', 'Carrying-cost proxy only: recon days and release-to-sale queues are not simulated. No invented stock replenishment.'),
 'service': prior('Service & fixed operations', [900,2200,4500], [500,2000,7000], 3, {'service_demand_lift':2,'service_capacity_lift':4,'service_value_lift':3,'admin_hours_saved':15}, 'Scheduling, inspection communication and approvals may improve throughput and approved work.', 'Enter service volume, capacity and gross per repair order first. Gross excludes technician/parts direct costs; no extra parts margin is added.'),
 'fi': prior('F&I', [400,1000,2200], [0,1000,3000], 3, {'fi_lift':3,'sales_capacity_lift':2,'admin_hours_saved':8}, 'Consistent product presentation and less manual work may improve backend gross and transaction capacity.', 'F&I gross must be separated from vehicle gross. No modeled lending decisions, compliance savings or guaranteed product penetration.'),
 'contract': prior('Contracting', [200,600,1500], [0,500,2000], 2, {'sales_capacity_lift':2,'admin_hours_saved':12}, 'Prefilled forms and electronic signing may reduce rework and processing effort.', 'No assumption about approval rates or funding interest savings. Allowance includes possible transaction charges; replace with actual terms.'),
 'analytics': prior('Analytics', [400,1200,3000], [500,2000,6000], 4, {'admin_hours_saved':20}, 'Consolidated reporting may release analysis time.', 'Information alone does not create sales. Revenue effects remain zero until a specific management intervention is modeled.'),
 'marketplace': prior('Marketplaces', [700,1800,4000], [0,250,1000], 2, {'capture_lift':5}, 'Additional inventory exposure may generate incremental unique inquiries.', 'Lead lift is net of assumed overlap. Subscriber tier, stock size and geography change price. Listings fees are separate from the paid-media budget.'),
}

def product(id, name, template, description, url, scope, claim='', extra_urls=None):
    p = copy.deepcopy(PRIORS[template])
    return {'id':id,'name':name,'category':p['category'],'description':description,'url':url,'checked':RESEARCH_DATE,
            'template':template,'scope':scope,'claim':claim,'extra_urls':extra_urls or [],'estimates':p,
            'price_evidence':'No comparable public price verified in this research; all amounts are analyst planning allowances.',
            'evidence':'Vendor website documents capabilities; numeric effects have low confidence and are not independently validated.',
            'availability':'Verify region, OEM, package and integrations with the vendor; catalogue inclusion is not certification.'}

CATALOG = [
 {'id':'custom','name':'Custom / existing solution','category':'Custom','description':'Create your own capability hypothesis.','url':'','checked':None},
 product('vin','VinSolutions Connect CRM','crm','Follow-up automation, unified customer records, mobile activity and reporting.','https://www.vinsolutions.com/dealership-software/connect-crm/','Core CRM workflow; separately priced add-ons excluded.'),
 product('drivecentric','DriveCentric Engagement Hub','crm','Unified calls, texts, email and video, with pipeline visibility and mobile workflows.','https://drivecentric.com/products/engagement-hub','Engagement Hub; AI agents and other add-ons excluded.',extra_urls=['https://drivecentric.com/request-pricing']),
 product('activix','Activix CRM','crm','Customer and internal communications with data connections to dealer systems.','https://www.activix.ca/en/crm/communications','CRM communications and workflow configuration.'),
 product('dealersocket','DealerSocket CRM','crm','Connected customer management spanning sales, desking, marketing and service.','https://dealersocket.com/products/crm/','CRM only; Inventory+ and DMS excluded.'),
 product('tekion','Tekion Automotive Retail Cloud','dms','Unified dealership platform spanning DMS, CRM, service, payments and analytics.','https://tekion.com/products','Core operational workflow; separately model any incremental CRM or service hypothesis.'),
 product('cdk','CDK Dealership Xperience','dms','Connected DMS and suites for retail, fixed operations, inventory and intelligence.','https://www.cdkglobal.com/','Core operational workflow, not every available suite.','Homepage promotes 25% more sales appointments with AI-assisted CRM workflows; not a general DMS treatment effect and not used as the preset.'),
 product('reynolds','Reynolds Retail Management System','dms','Retail management tools connect dealership sales, service, parts and business-office workflows.','https://www.reyrey.com/','Core operational workflow; specific optional modules excluded.','Homepage advertises 9.7% service-revenue growth among results; attribution and applicability are not established here.'),
 product('pbs','PBS Systems v10 APEX','dms','Integrated accounting, sales, service, parts, CRM and digital service tools.','https://www.pbssystems.com/dms','Core operational workflow; confirm contracted package.'),
 product('dealertrack','Dealertrack DMS','dms','Cloud accounting, service, parts and business-office workflows with third-party integrations.','https://us.dealertrack.com/content/dealertrack/en/dealer-management-solutions.html','DMS only; F&I contracting and optional add-ons excluded.'),
 product('360','360.Agency E-commerce 360','digital','Website and CRM-connected online vehicle-shopping and retailing capabilities.','https://360.agency/en/solutions-for-dealership/e-commerce-360/','Digital retailing workflow; separate website or CRM costs as applicable.'),
 product('d2c','D2C Media websites','website','Canadian dealer websites, search marketing, CRM and virtual BDC offerings.','https://www.d2cmedia.ca/en/','Website workflow only; separate managed marketing, CRM and BDC packages excluded.'),
 product('dealercom','Dealer.com websites','website','Personalized dealer websites, merchandising and connected shopping tools.','https://www.dealer.com/','Website package; precision advertising and managed services excluded.'),
 product('inspire','Dealer Inspire websites','website','Personalized websites and fast inventory search with connected retailing options.','https://www.carscommerce.inc/dealer-inspire/','Website workflow only; paid media and optional retailing excluded.','Vendor cites 15% higher close rate on pre-approved leads; this selected cohort is not a dealership-wide causal lift.'),
 product('dealeron','DealerOn Cosmos','website','Dealer websites, SEO and digital advertising services with merchandising tools.','https://www.dealeron.com/','Cosmos website workflow; SEO retainers and media excluded.'),
 product('glovebox','Vicimus GloveBox Websites','website','Customizable managed dealer websites with inventory and lead-management tools.','https://vicimus.com/products/glovebox-websites.html','Website workflow only.'),
 product('fullpath','Fullpath CDP + Audience Activation','retention','Unified shopper data supports personalized email and SMS journeys and CRM handoffs.','https://www.fullpath.com/dealership-audience-activation/','CDP plus activation scenario; paid advertising module excluded.',extra_urls=['https://www.fullpath.com/cdxp-data-experience-platform/']),
 product('bumper-retention','Vicimus Bumper Retention','retention','Lifecycle campaigns activate sales, service and unsold customers across communication channels.','https://vicimus.com/products/bumper-retention.html','Retention platform and campaign workflow; postage and media excluded.'),
 product('autoalert','AutoAlert data mining & engagement','retention','Buying-signal identification, service-to-sales alerts and targeted customer campaigns.','https://www.autoalert.com/','Data mining and engagement scenario; full CRM replacement excluded.'),
 product('mastermind','automotiveMastermind','retention','Predictive customer targeting, loyalty outreach and service-to-sales support.','https://www.automotivemastermind.com/','Predictive activation workflow; confirm data access and campaign costs.','Vendor advertises an average 8.3% loyalty lift and partner ROI figures; not imported as general causal effects.'),
 product('bumper-ads','Vicimus Bumper Inventory Ads','ads','Inventory-based Facebook and Google campaigns, creative generation and lead distribution.','https://vicimus.com/products/bumper-inventory-ads.html','Platform/management allowance; advertising media is entered separately.'),
 product('impel','Impel AI sales engagement','ai','Automotive lifecycle AI supports automated engagement and customer follow-up.','https://impel.ai/','Sales-engagement scenario; service AI and merchandising excluded.'),
 product('gubagoo','Gubagoo ChatSmart / engagement','ai','Online conversations and CRM-connected customer engagement with optional virtual retailing.','https://www.gubagoo.com/','Chat-engagement scenario; Virtual Retailing, Curator and F&I excluded.'),
 product('carnow','CarNow sales conversion','ai','Website conversations, intent signals and automated sales follow-up.','https://www.carnow.com/','Sales engagement scenario; service and digital retail packages excluded.'),
 product('calls-demand','Vicimus Calls on Demand','ai','BDC services support overflow, follow-up, appointments and reactivation.','https://vicimus.com/products/calls-on-demand.html','Sales BDC coverage allowance; actual volume and staffing terms must be quoted.'),
 product('vauto','vAuto Provision / ProfitTime','inventory','Market-informed appraisal, stocking and pricing guidance for vehicle inventory.','https://www.vauto.com/','Used-inventory pricing workflow; wholesale tools and iRecon excluded.','Homepage highlights 4.5% sales-volume and 17.3% frontend-gross increases with qualifications; preset uses smaller independent guesses.'),
 product('inventoryplus','DealerSocket Inventory+','inventory','Inventory search, configurable workflows, market comparisons and bulk pricing.','https://dealersocket.com/products/inventory-management/inventory-management/','Inventory management scenario only.'),
 product('irecon','vAuto iRecon','recon','Reconditioning coordination helps teams get vehicles ready for merchandising.','https://www.vauto.com/','Reconditioning workflow only; effects modeled as a carrying-cost proxy.'),
 product('xtime','Xtime Schedule + Inspect','service','Service scheduling and digital inspections support transparent recommendations and approvals.','https://xtime.com/inspect/','Scheduling and inspection scenario; confirm package and DMS integration.',extra_urls=['https://xtime.com/']),
 product('dealerfx','Dealer-FX Service Intelligence Platform','service','Scheduling, shop management, service marketing and insights connect fixed operations.','https://www.dealer-fx.com/','Service workflow scenario, with package scope to be confirmed.','Homepage reports 5% retention improvement and 9% cycle-time reduction; these are vendor claims, not preset inputs.'),
 product('mykaarma','myKaarma service lane','service','Service communications, scheduling, video inspection and payment workflows.','https://mykaarma.com/','Service workflow scenario; payment processing and extra modules may add fees.'),
 product('darwin','J.D. Power F&I Menu (Darwin)','fi','F&I product presentation, rating, contracting and signing with reporting.','https://www.jdpower.com/business/fi-menu/','F&I menu workflow; financing costs and aftermarket product costs excluded.'),
 product('bumper-finance','Vicimus Bumper Finance','fi','Customer payment and vehicle-customization experience bridges sales handoff and F&I.','https://vicimus.com/products/bumper-finance.html','Pre-F&I engagement scenario; not a full lender or contracting platform.'),
 product('routeone','RouteOne eContracting','contract','Credit-application data prepopulates contracts with digital signing and lender connections.','https://www.routeone.com/dealers/contracting/econtracting','Contracting workflow only; actual transaction and lender terms unverified.'),
 product('pie','Vicimus Pie','analytics','Unified departmental reporting, KPIs and diagnostics support management decisions.','https://vicimus.com/products/pie.html','Reporting and analysis-time scenario. Revenue changes require separate operational hypotheses.'),
 product('cars','Cars.com marketplace','marketplace','Inventory listings connect dealers with shoppers researching vehicle purchases.','https://www.carscommerce.inc/marketplace/','Listings allowance only; premium media and other Cars Commerce products excluded.'),
 product('cargurus','CarGurus Listings','marketplace','Listings packages promote dealer inventory and increase marketplace visibility.','https://dealers.cargurus.com/listings','Listings allowance only; tier and geography must be quoted.'),
 product('autotrader-ca','AutoTrader.ca dealer listings','marketplace','Canadian vehicle marketplace and dealer tools promote inventory to shoppers.','https://www.autotrader.ca/dealer/signup/','Canadian listings scenario; Instant Cash Offer and other products excluded.'),
]

# Expanded register reviewed separately; existing source dates are preserved.
PRIORS['indie_dms']=prior('DMS & operations',[150,400,1200],[0,500,3000],3,{},'Independent-dealer operating software budget. Start with cost only.','No sales or labor improvement is assumed. BHPH portfolio cash flows are not simulated. Confirm modules, transaction fees and hosting.')
PRIORS['indie_crm']=prior('CRM',[100,300,800],[0,300,1500],2,{},'Small-store CRM budget, without an assumed performance improvement.','Replace allowances with the actual package and usage fees. Existing CRM effects may already be reflected in the baseline.')
for key,label,cost in [('phone','Phones & call tracking',[150,600,1500]),('accounting','Accounting & payroll',[100,350,1000]),('payments','Payments',[50,200,600]),('parts','Parts inventory',[300,900,2000]),('reputation','Reviews & messaging',[200,500,1200])]:
    PRIORS[key]=prior(label,cost,[0,500,2000],2,{},'Budget-only starting point; add measured workload savings after review.','No automatic revenue, tax, compliance or labor saving. Confirm usage, seat and transaction fees; avoid duplicating existing bundled costs.')

def expanded(id,name,template,description,url,scope):
    item=product(id,name,template,description,url,scope)
    item['checked']='2026-09-15'
    item['connector_status']='No live connector; reviewed aggregate file workflow only. Browser compatibility untested.'
    return item

CATALOG += [
 expanded('dealercenter-dms','DealerCenter DMS','indie_dms','Independent-dealer inventory, desking, deal processing and reporting.','https://www.dealercenter.com/','DMS allowance only; confirm BHPH, CRM and website bundle boundaries.'),
 expanded('dealercenter-crm','DealerCenter CRM','indie_crm','Lead routing, tasks, text, email and phone communication.','https://www.dealercenter.com/','CRM only; confirm calling, text volumes and AI add-ons.'),
 expanded('dealercenter-bhph','DealerCenter BHPH','indie_dms','Portfolio, payment and collections workflows for in-house financing.','https://get.dealercenter.com/buy-here-pay-here/','BHPH module cost only; loan-book outcomes are not simulated. Do not duplicate bundled DMS fees.'),
 expanded('frazer','Frazer DMS','indie_dms','Used-car inventory, sales processing, forms, BHPH and accounting.','https://frazer.com/','Confirm desktop versus hosted package and payment charges. Browser collection cannot read desktop software.'),
 expanded('automanager','AutoManager DeskManager','indie_dms','Dealership management software for used-car operations.','https://www.automanager.com/','DeskManager package only; website and CRM products priced separately unless bundled.'),
 expanded('webmanager','AutoManager WebManager','website','Dealer websites and online inventory merchandising.','https://www.automanager.com/','Website workflow; confirm advertising and DMS bundle boundaries.'),
 expanded('waynereaves','Wayne Reaves PRO DMS','indie_dms','Independent-dealer inventory, sales, accounting and reporting.','https://www.waynereaves.com/','PRO DMS; confirm websites, marketing and optional services separately.'),
 expanded('idms','DealerSocket IDMS','indie_dms','Web-based independent and BHPH inventory, sales, customer and payment management.','https://inventoryplus.dealersocket.com/products/idms/','IDMS operating budget; no loan collection or default forecast.'),
 expanded('dealerbuilt','DealerBuilt Lightyear DMS','dms','DMS in the DealerBuilt portfolio for dealership operations.','https://dealerbuilt.com/','Lightyear only; Oplogic, iService and Vistadash are distinct package decisions.'),
 expanded('oplogic','DealerBuilt Oplogic CRM','crm','CRM and desking within the DealerBuilt product portfolio.','https://dealerbuilt.com/','Oplogic only; avoid duplicate cost if bundled with Lightyear.'),
 expanded('iservice','DealerBuilt iService','service','Service-lane tools in the DealerBuilt portfolio.','https://dealerbuilt.com/','Service workflow only; confirm DMS integration and contracted modules.'),
 expanded('vistadash','DealerBuilt Vistadash','analytics','Marketing analytics within the DealerBuilt portfolio.','https://dealerbuilt.com/','Reporting only; analytics does not automatically create revenue.'),
 expanded('dominion','Dominion VUE DMS','dms','Cloud dealer management system for dealership operations.','https://www.dominiondms.com/','Core DMS workflow; verify implementation and optional modules.'),
 expanded('quorum','Quorum DMS','dms','Fixed and variable operations, accounting, communications and analytics.','https://quorumdms.com/','Confirm regional and OEM support and bundled modules with vendor.'),
 expanded('autosoft','Autosoft DMS','dms','Integrated inventory, sales, financing and fixed operations.','https://autosoftdms.com/platform/autosoft-dms/','Core DMS; confirm platform edition, hosting and integrations.'),
 expanded('dealerteam','DealerTeam DMS','dms','Salesforce-based dealer management for sales, service, parts and accounting.','https://www.dealerteam.com/','Confirm platform licensing and implementation; Salesforce costs may be separate.'),
 expanded('dealerpull','Dealerpull DMS','indie_dms','Car dealer management software and connected operating workflows.','https://www.dealerpull.com/','Confirm country, forms, accounting and subscription edition.'),
 expanded('selly','Selly Automotive CRM','indie_crm','CRM and lead management for independent and used-car dealers.','https://www.sellyautomotive.com/','CRM only; confirm messaging and calling usage fees.'),
 expanded('promax','ProMax','crm','Retail platform for dealership sales and customer workflows.','https://www.promaxunlimited.com/','CRM/desking hypothesis only; credit services and other products may be separate.'),
 expanded('dealerpeak','DealerPeak CRM','crm','Customer management, desking and reporting for stores and dealer groups.','https://www.dealerpeak.com/','CRM only; verify multi-rooftop licensing and integrations.'),
 expanded('dealercarsearch','Dealer Car Search','website','Dealer websites and online inventory tools.','https://www.dealercarsearch.com/','Website package only; confirm CRM and marketing bundle boundaries.'),
 expanded('callrail','CallRail','phone','Call tracking and marketing-source attribution.','https://www.callrail.com/call-tracking','Call tracking budget; number rental, minutes and intelligence add-ons may be extra.'),
 expanded('callrevu','CallRevu','phone','Automotive phone, lead management and conversation analytics tools.','https://www.callrevu.com/','Choose a quoted package; do not assume the allowance includes every suite.'),
 expanded('carwars','Car Wars','phone','Automotive call tracking and phone traffic reporting.','https://carwars.com/main/','Call tracking workflow; additional phone and AI services require confirmation.'),
 expanded('podium','Podium messaging & reviews','reputation','Customer texting and review invitation workflows.','https://www.podium.com/customer-stories/carizma-motors','Messaging and reviews only. Published customer case results are not model effects.'),
 expanded('rapidrecon','Rapid Recon','recon','Reconditioning workflow and vehicle preparation status tracking.','https://rapidrecon.com/','Recon workflow only; carrying-cost effects remain category assumptions.'),
 expanded('dealerlogix','Dealerlogix','service','Service scheduling, inspections, write-ups and customer communication.','https://dealerlogix.com/','Service-lane package; confirm payments and pickup/delivery options.'),
 expanded('tekmetric','Tekmetric','service','Auto repair shop management software.','https://www.tekmetric.com/','Independent repair operation; OEM warranty and franchise compatibility not assumed.'),
 expanded('shopmonkey','Shopmonkey','service','Repair-shop management and customer workflows.','https://www.shopmonkey.io/','Repair operation only; confirm dealership DMS and OEM compatibility.'),
 expanded('partsedge','PartsEdge','parts','Dealership parts inventory management tools.','https://www.partsedge.com/','Budget only: parts aging, obsolescence and counter-sales revenue are not separately simulated.'),
 expanded('dealerpay','Dealer Pay','payments','Dealership payment processing and reconciliation tools.','https://dealer-pay.com/','Software allowance excludes processing percentages, card fees and hardware. No surcharge savings assumed.'),
 expanded('quickbooks','QuickBooks Online Payroll','accounting','Payroll processing within the QuickBooks product family.','https://quickbooks.intuit.com/learn-support/en-us/help-article/payroll/jump-quickbooks-online-payroll/L76fcUeLc_US_en_US','Payroll allowance; country edition, employee fees and accounting subscription require confirmation.'),
 expanded('adp','ADP Payroll','accounting','Payroll processing with time and HR options.','https://www.adp.com/what-we-offer/payroll.aspx','Budget varies by staff count, pay frequency and service package; no compliance guarantee modeled.'),
 expanded('lotlinx','Lotlinx','inventory','Automotive inventory management and market intelligence.','https://www.lotlinx.com/','Inventory hypothesis only; confirm advertising services and media costs separately.'),
]

def estimated_module(vendor, case='working'):
    from .operating import task_estimates
    item = next(x for x in CATALOG if x['id']==vendor)
    if 'estimates' not in item:
        raise ValueError('Custom modules have no researched estimate.')
    if case not in ['downside','no-benefit','cautious','working','optimistic']:
        raise ValueError('Unknown estimate case.')
    p=item['estimates']
    factor={'downside':-.5,'no-benefit':0,'cautious':.5,'working':1,'optimistic':2}[case]
    effects={k:round(p['effects'].get(k,0)*factor,2) for k in EFFECT_LABELS}
    return dict(task_savings=task_estimates(vendor,case),cost_scope='rooftop',vendor=vendor,name=item['name'],monthly_cost=p['monthly_range'][2 if case=='downside' else 1],setup_cost=p['setup_range'][2 if case=='downside' else 1],adoption=p['adoption'],ramp_months=p['ramp_months'],integration=80,enabled=True,estimate_case=case,**effects,
        rationale=f"Analyst estimate ({case}), catalogue {CATALOGUE_VERSION}; low confidence, not vendor pricing or validated performance. {p['reasoning']} Package: {item['scope']} Costs are nominal allowances in the chosen model currency; no FX conversion. Source: {item['url']}")


def catalogue_export(format='csv', currency='USD'):
    import csv, io, json
    if format not in ('csv','json') or currency not in ('USD','CAD'):raise ValueError('Choose CSV or JSON and USD or CAD.')
    products=[x for x in CATALOG if x.get('estimates')]
    notice='Analyst planning allowances, not verified vendor prices or measured effects. Nominal model currency; no FX conversion. No live connectors.'
    if format=='json':return json.dumps(dict(catalogue_version=CATALOGUE_VERSION,currency=currency,notice=notice,products=products),indent=2).encode('utf-8'),'application/json'
    out=io.StringIO(newline='');w=csv.writer(out)
    w.writerow(['Product','Category','Description','Package scope','Source URL','Source reviewed','Currency (nominal)','Monthly low','Monthly working','Monthly high','Setup low','Setup working','Setup high','Working effects (hypotheses)','Limitations','Price evidence','Connection status','Catalogue version'])
    for x in products:
        p=x['estimates'];w.writerow([x['name'],x['category'],x['description'],x['scope'],x['url'],x['checked'],currency,*p['monthly_range'],*p['setup_range'],json.dumps(p['effects']),p['limitations'],x['price_evidence'],'No live connector; reviewed aggregate workflow only',CATALOGUE_VERSION])
    return out.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8'
