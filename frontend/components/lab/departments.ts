// Department descriptions from Composite 263e1c7; no calculation logic.
export const departments: [string,string,string,string[]][] = [
 ['management','Leadership & management','Planning, daily meetings, department reviews and owner reporting.',['Daily manager meeting','Monthly financial review']],
 ['sales','Vehicle sales & delivery','New, used and fleet sales; trade appraisals, demonstrations and deliveries.',['Vehicle demonstration','Delivery handover']],
 ['bdc','BDC & customer care','Incoming calls, lead response, appointments and customer follow-up.',['Appointment confirmation','Missed-call follow-up']],
 ['fi','Finance & insurance','Credit applications, lender submissions, disclosures and deal funding.',['Funding follow-up','Product cancellation processing']],
 ['collections','BHPH credit & collections','Underwriting, payment reminders, delinquency work, repossession coordination and recoveries.',['Credit application review','Payment reminder','Delinquency review','Repossession coordination']],
 ['inventory','Buying & inventory','Auction sourcing, private purchases, appraisals, transport, aging and merchandising.',['Auction buying review','Transport coordination','Inventory aging review']],
 ['service','Service & warranty','Service reception, diagnostics, repair work, warranty administration and customer approvals.',['Warranty claim administration','Service quality check']],
 ['parts','Parts & accessories','Ordering, receiving, counter sales, stock counts, returns and obsolete stock.',['Parts stock count','Supplier return processing']],
 ['recon','Reconditioning & detail','Recon scheduling, cosmetic preparation, cleaning and ready-for-sale checks.',['Vehicle detail','Ready-for-sale inspection']],
 ['collision','Collision & body shop','Estimates, insurer communication, repair coordination and quality control.',['Collision estimate preparation','Insurer update']],
 ['marketing','Marketing & reputation','Campaign planning, creative, website listings, reviews and lead-source analysis.',['Review response','Campaign performance review']],
 ['admin','Accounting, titles & administration','Payables, receivables, title/registration, reconciliations and month-end close.',['Title and registration processing','Month-end close']],
 ['hr','People & training','Recruitment, onboarding, schedules, benefits and employee development.',['Employee onboarding','Staff training session']],
 ['compliance','Compliance & risk','License renewals, deal-file checks, privacy, complaints and safety records.',['Deal-file compliance check','Safety inspection']],
 ['it','IT & systems','Access, devices, data quality, integrations, backups and security administration.',['User access review','Data quality review']],
 ['facilities','Facilities & lot operations','Building, lot, utilities, equipment, cleaning, grounds, security and waste.',['Facility inspection','Lot and building maintenance']],
 ['fleet','Fleet, rental & loaners','Commercial accounts, fleet delivery, loaner scheduling and vehicle returns.',['Fleet account review','Loaner return inspection']]
];
export const roleDepartments:Record<string,string> = {management:"management",sales:"sales",bdc:"bdc",fi:"fi",advisors:"service",technicians:"service",parts:"parts",admin:"admin",porters:"recon"};
