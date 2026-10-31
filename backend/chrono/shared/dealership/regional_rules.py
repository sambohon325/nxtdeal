"""Sourced rule summaries and explicit gaps; no inferred permission to operate."""

def rules(country, region):
    result=[]
    def add(topic, summary, source, status='Reference only', impact='Review the related operating assumptions; no automatic cost applied.'):
        result.append(dict(topic=topic,summary=summary,source=source,status=status,impact=impact,checked='2026-09-15'))
    if country=='United States':
        add('Used-vehicle disclosures',
            'Maine and Wisconsin use similar state disclosure rules instead of the FTC Used Car Rule.' if region in ['Maine','Wisconsin'] else
            'The FTC Used Car Rule requires Buyers Guides for covered used-vehicle dealers. Vehicle-size and other exemptions matter for specialty inventory; consignment can be covered.',
            'https://www.ftc.gov/business-guidance/resources/dealers-guide-used-car-rule',
            impact='Allow staff time for disclosures and warranty administration; a vehicle class is not yet evaluated automatically.')
        add('Dealership overtime exemptions','Federal overtime exemptions can cover certain sales, parts, mechanic and service-advisor roles. Eligibility depends on duties and establishment; state protections can differ. The simulator does not automatically exempt a role.',
            'https://www.dol.gov/agencies/whd/fact-sheets/11-flsa-auto-dealers',
            impact='Hours & costs uses your entered weekly threshold and multiplier. Daily overtime, exemptions and regular-rate adjustments are not calculated.')
        add(region+' employment rules','Check this state’s labor authority for local wage rates, daily overtime, breaks, leave and commission agreements. The general wage floor and income-tax proxy are loaded separately.',
            'https://www.dol.gov/agencies/whd/state/contacts','Detailed rules not loaded')
        add(region+' dealer licensing / DTC / lending','Dealer license class, OEM direct-sales eligibility, consumer-credit limits, bonds, inspections and document-fee caps have not been fully verified for this state. Unknown does not mean unrestricted.',
            'https://www.usa.gov/state-consumer','Detailed rules not loaded',
            'Enter verified costs below. DTC and BHPH results are conditional planning scenarios, not legal eligibility decisions.')
        if region=='Texas':
            add('Texas manufacturer ownership','Texas Occupations Code 2301.476 restricts manufacturer ownership or operation of dealerships, subject to statutory exceptions. Confirm the actual OEM and transaction structure.',
                'https://tcss.legis.texas.gov/Docs/OC/htm/OC.2301.htm',impact='DTC preset is a hypothetical retail budget; it does not establish permission for Texas sales.')
    else:
        add(region+' employment standards','Use the province or territory’s employment standards, including occupational exceptions, when setting overtime, breaks and paid leave. A federal employment threshold is not assumed for this dealership.',
            'https://www.canada.ca/en/services/jobs/workplace/federally-regulated-industries.html',
            'Detailed rules not loaded','The regional wage floor is available. Weekly overtime remains your editable assumption; daily overtime and leave accruals are not automated.')
        add(region+' consumer / dealer regulation','The official directory identifies this jurisdiction’s consumer authority. Dealer licensing, lending, vehicle inspections, fee rules and warranty obligations require transaction-specific verification.',
            'https://ised-isde.canada.ca/site/office-consumer-affairs/en/federal-provincial-and-territorial-consumer-affairs-offices',
            'Detailed rules not loaded','Add verified licensing and compliance expenses to monthly or per-sale costs below; zero means excluded.')
        if region=='Ontario':
            add('Ontario all-in advertised pricing','OMVIC-regulated dealer advertisements must include required fees in the advertised price, with permitted exclusions such as HST and licensing. Manufacturer advertisements are outside OMVIC’s regulation.',
                'https://www.omvic.ca/buying/your-rights/all-in-price-advertising/',impact='Review advertised prices and mandatory fees; the simulator does not validate advertising copy.')
        if region=='Alberta':
            add('Alberta all-in advertised pricing','AMVIC describes the requirement to include vehicle fees and charges in the advertised total, excluding GST and financing-related costs.',
                'https://www.amvic.org/website-disclaimers-and-all-in-advertised-pricing/',impact='Include dealer-paid charges in unit economics; advertising compliance is not automatic.')
        if region=='Quebec':
            add('Quebec used-vehicle warranty','The warranty of good working order applies to qualifying used vehicles; age and mileage determine coverage. Other legal warranties can also apply.',
                'https://www.opc.gouv.qc.ca/en/consumer/good-service/vehicle/car-purchase/used/warranty/warranty-fitness',impact='Allow warranty expense in gross or per-sale cost. Vehicle age and mileage are not yet modeled.')
    return result
