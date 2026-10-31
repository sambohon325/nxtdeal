"""Dated jurisdiction references and deliberately limited budgeting rules."""
import copy

CHECKED = '2026-09-15'
SOURCES = [
 dict(name='US Department of Labor: state wage table',url='https://www.dol.gov/agencies/whd/mw-consolidated',description='General adult wage references, July 1, 2026 table. Local rates and occupational exemptions require separate treatment.',checked=CHECKED),
 dict(name='National Payroll Institute: Canadian minimum wages',url='https://payroll.ca/minimum-wage-updates',description='General provincial and territorial rates effective September 15, 2026. Later announced increases are not advanced automatically.',checked=CHECKED),
 dict(name='CRA: corporation tax rates',url='https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/corporations/corporation-tax-rates.html',description='General federal and provincial rates. Small-business eligibility is not assumed from dealership size.',checked=CHECKED),
 dict(name='Alberta: corporate tax rates',url='https://www.alberta.ca/about-tax-levy-rates-prescribed-interest-rates',description='General provincial corporation rate of 8%.',checked=CHECKED),
 dict(name='Revenu Quebec: general and small-business tax',url='https://www.revenuquebec.ca/en/press-room/tax-news/details/2026-05-04/increase-in-the-small-business-deduction-rate/',description='General rate 11.5%; lower rates require eligibility that this simulator does not determine.',checked=CHECKED),
 dict(name='IRS: corporations',url='https://www.irs.gov/publications/p542',description='21% federal C-corporation rate. Pass-through businesses require a custom planning rate.',checked=CHECKED),
 dict(name='Tax Foundation: 2026 state corporation rates',url='https://taxfoundation.org/data/all/state/state-corporate-income-tax-rates-brackets/',description='Secondary compilation, April 2026. Top rates are planning proxies, not effective tax rates; brackets, exemptions, minimum taxes and apportionment are not implemented.',checked=CHECKED),
 dict(name='Utah: 2026 rate update',url='https://tax.utah.gov/forms-pubs-revisions/',description='2026 income-tax rate update to 4.45%.',checked=CHECKED),
 dict(name='Georgia: business incentives',url='https://georgia.org/business-support/incentives',description='Reports a 4.99% 2026 corporate rate; older DOR overview still reports 5.19%. Treat as a planning assumption pending return-specific verification.',checked=CHECKED),
]

# General adult wage and general provincial corporate rate, as of CHECKED.
CA = {
 'Alberta':(15,8), 'British Columbia':(18.25,12), 'Manitoba':(16,12),
 'New Brunswick':(15.90,14), 'Newfoundland and Labrador':(16.35,15),
 'Northwest Territories':(17.20,11.5), 'Nova Scotia':(16.75,14),
 'Nunavut':(20.17,12), 'Ontario':(17.60,11.5), 'Prince Edward Island':(17,15),
 'Quebec':(16.60,11.5), 'Saskatchewan':(15.35,12), 'Yukon':(18.51,12),
}
# USD general wage (federal floor for covered employment where higher), top income rate proxy.
US = {
 'Alabama':(7.25,6.5),'Alaska':(14,9.4),'Arizona':(15.15,4.9),'Arkansas':(11,4.3),
 'California':(16.90,8.84),'Colorado':(15.16,4.4),'Connecticut':(16.94,8.25),
 'Delaware':(15,8.7),'District of Columbia':(18.40,8.25),'Florida':(14,5.5),
 'Georgia':(7.25,4.99),'Hawaii':(16,6.4),'Idaho':(7.25,5.3),'Illinois':(15,9.5),
 'Indiana':(7.25,4.9),'Iowa':(7.25,7.1),'Kansas':(7.25,7),'Kentucky':(7.25,5),
 'Louisiana':(7.25,5.5),'Maine':(15.10,8.93),'Maryland':(15,8.25),
 'Massachusetts':(15,8),'Michigan':(13.73,6),'Minnesota':(11.41,9.8),
 'Mississippi':(7.25,5),'Missouri':(15,4),'Montana':(10.85,6.75),
 'Nebraska':(15,4.55),'Nevada':(12,0),'New Hampshire':(7.25,7.5),
 'New Jersey':(15.92,11.5),'New Mexico':(12,5.9),'New York':(16,7.25),
 'North Carolina':(7.25,2),'North Dakota':(7.25,4.31),'Ohio':(11,0),
 'Oklahoma':(7.25,4),'Oregon':(15.55,7.6),'Pennsylvania':(7.25,7.49),
 'Rhode Island':(16,7),'South Carolina':(7.25,5),'South Dakota':(11.85,0),
 'Tennessee':(7.25,6.5),'Texas':(7.25,0),'Utah':(7.25,4.45),
 'Vermont':(14.42,8.5),'Virginia':(12.77,6),'Washington':(17.13,0),
 'West Virginia':(8.75,6.5),'Wisconsin':(7.25,7.9),'Wyoming':(7.25,0),
}

def reference(country, region):
    table = CA if country == 'Canada' else US
    if country not in ['Canada','United States'] or region not in table:
        raise ValueError('Choose a province or state belonging to the selected country.')
    wage, tax = table[region]
    notes = ['Snapshot as of '+CHECKED+'; rates stay fixed throughout the experiment.',
             'General wage floor is a budgeting option for hourly roles only. Local rates, salary/commission tests, overtime exemptions and dealer licensing are not evaluated.']
    if country == 'Canada':
        notes.append('General corporation rate; small-business deductions, credits and associated-company limits are excluded.')
    else:
        notes.append('State top-rate proxy plus federal C-corporation rate, assuming state income tax is federally deductible. This does not calculate tax brackets or an actual return.')
    if region in ['Delaware','Nevada','Ohio','Oregon','Tennessee','Texas','Washington']:
        notes.append('This state has a gross-receipts or franchise-style tax not calculated here. Enter a monthly additional tax allowance; zero means excluded, not tax-free.')
    if region == 'New York': notes.append('NYC, Nassau, Suffolk and Westchester wage reference is $17; default $16 is for the rest of the state. Override the floor for the location.')
    if region == 'Oregon': notes.append('Standard wage area $15.55; Portland $16.80; nonurban $14.55. Override for the location.')
    if region == 'Georgia': notes.append('Official pages disagree: incentives page says 4.99% for 2026, older DOR summary says 5.19%; verify or override.')
    from .regional_rules import rules
    from .wages import benchmarks
    return dict(rules=rules(country,region),wages=benchmarks(country,region),country=country,region=region,currency='CAD' if country=='Canada' else 'USD',checked=CHECKED,
                minimum_wage=wage,regional_tax=tax,federal_tax=15 if country=='Canada' else 21,
                combined_tax=round(15+tax if country=='Canada' else 21+tax*.79,4),notes=notes)

def regional_defaults(country, region):
    r=reference(country,region)
    return dict(wage_floor=r['minimum_wage'],apply_wage_floor=True,tax_rate=r['combined_tax'],
                tax_enabled=True,extra_monthly_cost=0,extra_cost_per_sale=0,notes='General corporate planning scenario; replace with dealer-specific rates and regulatory costs.')

def catalogue():
    return {country:{region:reference(country,region) for region in table} for country,table in [('Canada',CA),('United States',US)]}
