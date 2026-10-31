"""
Generates a realistic demo/test dataset for NXTDeal. Expanded 2026-07-13 (session 39)
per Sam: "lets add more data... 500 cars, 1000 leads, 500 customers, some with service,
some in marketing for events, etc" plus a realistic employee roster "for a typical
medium size franchise and used car dealer that also has inhouse financing" and vehicles/
contracts/finance "in various states of sale/close/stage" -- see BUILD_QUEUE.md session
39 for the full design notes (superseding the original 100/100/100/25-record dataset from
session 16, extended with parts/part-sales in session 35).

This writes CSVs into backend/seed_data/ matching the exact column names each existing
imports/*.py script expects (dict(row) becomes the entity's attributes verbatim, so
column names ARE the attribute names) -- it does not touch the graph itself. Run
backend/run_seed_import.py afterward to actually load these into storage/graph.json (that
script also seeds a batch of real, in-flight Deal Desk deals / campaigns / assets via
imports/seed_operational.py -- see that module for the "various stages of close" pieces
that don't fit a flat CSV shape).

Stdlib only (random/csv/datetime) -- no Faker or pandas, matching the project's existing
zero-extra-dependency import scripts. Uses a fixed random seed so re-running this
produces the same dataset (useful if you want to regenerate after tweaking something
below rather than getting a completely different dealership each time).
"""

import csv
import os
import random
from datetime import date, timedelta

random.seed(42)

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "seed_data"
)

TODAY = date(2026, 7, 13)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Margaret", "Anthony", "Betty", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Dorothy", "Andrew", "Kimberly", "Paul", "Emily", "Joshua", "Donna",
    "Kenneth", "Michelle", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Laura",
    "Jeffrey", "Sharon", "Ryan", "Cynthia", "Jacob", "Amy", "Gary", "Angela",
    "Nicholas", "Shirley", "Eric", "Anna", "Jonathan", "Ruth", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Nicole", "Scott", "Katherine", "Brandon", "Samantha",
    "Benjamin", "Christine", "Samuel", "Emma", "Gregory", "Catherine", "Alexander",
    "Debra", "Frank", "Virginia", "Raymond", "Rachel", "Jack", "Carolyn", "Dennis",
    "Janet", "Jerry", "Maria", "Tyler", "Victor", "Alice", "Roger", "Julia",
    "Keith", "Gloria", "Terry", "Diane", "Sean", "Judith", "Adam", "Joan",
    "Austin", "Evelyn", "Wayne", "Kathleen", "Ralph", "Marie", "Roy", "Andrea",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
    "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey",
    "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson", "Watson",
    "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz",
    "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long",
    "Ross", "Foster", "Jimenez", "Powell", "Jenkins", "Perry", "Russell", "Sullivan",
    "Bell", "Coleman", "Butler", "Henderson", "Barnes", "Gonzales", "Fisher", "Vasquez",
]

CITIES = [
    ("Austin", "TX", "787"), ("Dallas", "TX", "752"), ("Fort Worth", "TX", "761"),
    ("San Antonio", "TX", "782"), ("Round Rock", "TX", "786"), ("Georgetown", "TX", "786"),
    ("Cedar Park", "TX", "786"), ("Pflugerville", "TX", "786"), ("Waco", "TX", "767"),
    ("Killeen", "TX", "765"), ("Temple", "TX", "765"), ("San Marcos", "TX", "786"),
    ("Leander", "TX", "786"), ("Hutto", "TX", "786"), ("Belton", "TX", "765"),
]

VEHICLES = [
    ("Toyota", "Camry"), ("Toyota", "RAV4"), ("Toyota", "Highlander"),
    ("Toyota", "Tacoma"), ("Toyota", "Corolla"),
    ("Honda", "Accord"), ("Honda", "CR-V"), ("Honda", "Civic"), ("Honda", "Pilot"),
    ("Ford", "F-150"), ("Ford", "Explorer"), ("Ford", "Escape"), ("Ford", "Bronco"),
    ("Ford", "Mustang"),
    ("Chevrolet", "Silverado 1500"), ("Chevrolet", "Equinox"), ("Chevrolet", "Tahoe"),
    ("Chevrolet", "Malibu"),
    ("Jeep", "Grand Cherokee"), ("Jeep", "Wrangler"), ("Jeep", "Compass"),
    ("Ram", "1500"),
    ("Hyundai", "Tucson"), ("Hyundai", "Santa Fe"), ("Hyundai", "Elantra"),
    ("Kia", "Sportage"), ("Kia", "Telluride"), ("Kia", "K5"),
    ("Nissan", "Altima"), ("Nissan", "Rogue"), ("Nissan", "Frontier"),
    ("GMC", "Sierra 1500"), ("GMC", "Terrain"),
    ("Subaru", "Outback"), ("Subaru", "Forester"),
]

BHPH_VEHICLES = [
    ("Chevrolet", "Impala"), ("Chevrolet", "Cruze"), ("Chevrolet", "Malibu"),
    ("Ford", "Fusion"), ("Ford", "Focus"), ("Ford", "Escape"),
    ("Nissan", "Altima"), ("Nissan", "Sentra"), ("Nissan", "Versa"),
    ("Hyundai", "Sonata"), ("Hyundai", "Elantra"),
    ("Kia", "Optima"), ("Kia", "Soul"),
    ("Toyota", "Corolla"), ("Toyota", "Camry"),
    ("Dodge", "Charger"), ("Dodge", "Journey"),
    ("Chrysler", "200"), ("Chrysler", "300"),
    ("Jeep", "Patriot"), ("Jeep", "Compass"),
    ("Buick", "LaCrosse"), ("GMC", "Terrain"),
]

TRIMS = ["Base", "SE", "SEL", "Sport", "Limited", "Premium", "XLT", "Platinum", "LT", "LS"]

COLORS = [
    "Alpine White", "Midnight Black", "Silver Metallic", "Storm Gray", "Deep Blue",
    "Crimson Red", "Champagne", "Forest Green", "Slate", "Pearl White", "Graphite",
]

LENDERS_BRAND_MATCHED = {
    "Toyota": "Toyota Financial Services",
    "Honda": "Honda Financial Services",
    "Ford": "Ford Credit",
    "Chevrolet": "GM Financial",
    "GMC": "GM Financial",
    "Buick": "GM Financial",
    "Jeep": "Chrysler Capital",
    "Ram": "Chrysler Capital",
    "Dodge": "Chrysler Capital",
    "Chrysler": "Chrysler Capital",
    "Hyundai": "Hyundai Motor Finance",
    "Kia": "Kia Finance America",
    "Nissan": "Nissan Motor Acceptance",
    "Subaru": "Subaru Motors Finance",
}

THIRD_PARTY_LENDERS = [
    "Ally Financial", "Chase Auto Finance", "Capital One Auto Finance",
    "Community Auto Credit Union"
]

IN_HOUSE_LENDER_NAME = "In-House Financing (BHPH)"

SERVICE_DESCRIPTIONS = [
    "Oil Change", "Tire Rotation", "Multi-Point Inspection", "Brake Pad Replacement",
    "Recall Repair - Airbag Sensor", "Battery Replacement", "Cabin Air Filter Replacement",
    "Wiper Blade Replacement", "Software/Firmware Update", "Wheel Alignment",
    "Coolant Flush", "Transmission Service", "Recall Repair - Fuel Pump",
    "AC System Service", "Serpentine Belt Replacement", "Spark Plug Replacement",
    "Check Engine Light Diagnosis", "Tire Replacement (Set of 4)", "State Inspection",
]

LEAD_SOURCES = [
    "Website", "Walk-In", "Phone Inquiry", "Referral", "Autotrader", "Cars.com",
    "Trade Show", "Service Drive", "Facebook Marketplace", "CarGurus",
]

LEAD_SOURCE_WEIGHTS = [22, 14, 14, 10, 12, 10, 3, 6, 6, 3]

LEAD_STATUSES = ["New", "Contacted", "Qualified", "Nurturing", "Lost"]
LEAD_STATUS_WEIGHTS = [28, 24, 15, 20, 13]

PART_CATALOG = [
    ("Oil Filter", "Filters"), ("Air Filter", "Filters"), ("Cabin Air Filter", "Filters"),
    ("Fuel Filter", "Filters"),
    ("Front Brake Pads", "Brakes"), ("Rear Brake Pads", "Brakes"),
    ("Brake Rotor", "Brakes"), ("Brake Caliper", "Brakes"),
    ("Motor Oil (Case)", "Fluids"), ("Coolant", "Fluids"), ("Transmission Fluid", "Fluids"),
    ("Windshield Washer Fluid", "Fluids"),
    ("Wiper Blade Set", "Accessories"), ("Floor Mat Set", "Accessories"),
    ("Cargo Liner", "Accessories"), ("Roof Rack Crossbar", "Accessories"),
    ("Battery", "Electrical"), ("Alternator", "Electrical"), ("Starter Motor", "Electrical"),
    ("Headlight Assembly", "Body"), ("Tail Light Assembly", "Body"),
    ("Bumper Cover", "Body"), ("Side Mirror Assembly", "Body"),
    ("Serpentine Belt", "Engine"), ("Spark Plug Set", "Engine"), ("Timing Belt Kit", "Engine"),
    ("Radiator", "Engine"), ("Water Pump", "Engine"),
    ("Tire (Passenger)", "Tires"), ("Tire (Light Truck)", "Tires"),
]

PART_SALE_CUSTOMER_TYPES = ["Retail", "Wholesale", "Internal", "Warranty"]


def _random_date(start, end):

    span_days = (end - start).days

    return start + timedelta(days=random.randint(0, max(span_days, 0)))


def _recency_biased_date(start, end, recent_days=30, recent_weight=0.35):

    if random.random() < recent_weight and (end - timedelta(days=recent_days)) > start:
        return _random_date(end - timedelta(days=recent_days), end)

    return _random_date(start, end)


def _phone():

    return f"512-555-01{random.randint(0, 99):02d}"


def _vin(make, model, index):

    make_code = "".join(ch for ch in make.upper() if ch.isalnum())[:3]
    model_code = "".join(ch for ch in model.upper() if ch.isalnum())[:3]

    return f"{make_code}{model_code}{index:05d}"


def _monthly_payment(amount_financed, apr, term_months):

    monthly_rate = apr / 100 / 12

    if monthly_rate == 0:
        return round(amount_financed / term_months, 2)

    payment = (
        amount_financed
        * monthly_rate
        / (1 - (1 + monthly_rate) ** (-term_months))
    )

    return round(payment, 2)


EMPLOYEES = [
    {"EmployeeID": "E3001", "FirstName": "Alicia", "LastName": "Ramirez", "Department": "Operations", "Title": "General Manager", "Email": "alicia.ramirez@example.com"},
    {"EmployeeID": "E3002", "FirstName": "Grant", "LastName": "Whitfield", "Department": "Operations", "Title": "Assistant General Manager", "Email": "grant.whitfield@example.com"},
    {"EmployeeID": "E3003", "FirstName": "Renee", "LastName": "Ostrowski", "Department": "Operations", "Title": "Comptroller", "Email": "renee.ostrowski@example.com"},
    {"EmployeeID": "E3004", "FirstName": "Malik", "LastName": "Freeman", "Department": "Operations", "Title": "HR Coordinator", "Email": "malik.freeman@example.com"},
    {"EmployeeID": "E3005", "FirstName": "Dana", "LastName": "Whitfield", "Department": "Operations", "Title": "Title & Registration Clerk", "Email": "dana.whitfield@example.com"},
    {"EmployeeID": "E3044", "FirstName": "Sonya", "LastName": "Blackwood", "Department": "Operations", "Title": "Front Desk Receptionist", "Email": "sonya.blackwood@example.com"},
    {"EmployeeID": "E3045", "FirstName": "Grady", "LastName": "Pham", "Department": "Operations", "Title": "Receptionist / Cashier", "Email": "grady.pham@example.com"},
    {"EmployeeID": "E3006", "FirstName": "Derek", "LastName": "Coleman", "Department": "Sales", "Title": "Sales Manager", "Email": "derek.coleman@example.com"},
    {"EmployeeID": "E3007", "FirstName": "Trevor", "LastName": "Aldana", "Department": "Sales", "Title": "Used Car Sales Manager", "Email": "trevor.aldana@example.com"},
    {"EmployeeID": "E3008", "FirstName": "Priya", "LastName": "Nair", "Department": "Sales", "Title": "Sales Consultant", "Email": "priya.nair@example.com"},
    {"EmployeeID": "E3009", "FirstName": "Marcus", "LastName": "Bell", "Department": "Sales", "Title": "Sales Consultant", "Email": "marcus.bell@example.com"},
    {"EmployeeID": "E3010", "FirstName": "Grace", "LastName": "Kim", "Department": "Sales", "Title": "Sales Consultant", "Email": "grace.kim@example.com"},
    {"EmployeeID": "E3011", "FirstName": "Omar", "LastName": "Farouk", "Department": "Sales", "Title": "Sales Consultant", "Email": "omar.farouk@example.com"},
    {"EmployeeID": "E3012", "FirstName": "Isabella", "LastName": "Cruz", "Department": "Sales", "Title": "Sales Consultant", "Email": "isabella.cruz@example.com"},
    {"EmployeeID": "E3013", "FirstName": "Trent", "LastName": "Whitaker", "Department": "Sales", "Title": "Sales Consultant", "Email": "trent.whitaker@example.com"},
    {"EmployeeID": "E3014", "FirstName": "Nadia", "LastName": "Volkov", "Department": "Sales", "Title": "Sales Consultant", "Email": "nadia.volkov@example.com"},
    {"EmployeeID": "E3015", "FirstName": "Corey", "LastName": "Banks", "Department": "Sales", "Title": "Used Car Sales Consultant", "Email": "corey.banks@example.com"},
    {"EmployeeID": "E3016", "FirstName": "Selena", "LastName": "Marsh", "Department": "Sales", "Title": "Used Car Sales Consultant", "Email": "selena.marsh@example.com"},
    {"EmployeeID": "E3017", "FirstName": "Hannah", "LastName": "Osei", "Department": "Sales", "Title": "Internet Sales / BDC Rep", "Email": "hannah.osei@example.com"},
    {"EmployeeID": "E3018", "FirstName": "Julian", "LastName": "Pratt", "Department": "Sales", "Title": "Internet Sales / BDC Rep", "Email": "julian.pratt@example.com"},
    {"EmployeeID": "E3019", "FirstName": "Vince", "LastName": "Delgado", "Department": "Sales", "Title": "Lot Attendant", "Email": "vince.delgado@example.com"},
    {"EmployeeID": "E3020", "FirstName": "Denise", "LastName": "Walsh", "Department": "Finance", "Title": "F&I Director", "Email": "denise.walsh@example.com"},
    {"EmployeeID": "E3021", "FirstName": "Harold", "LastName": "Ibekwe", "Department": "Finance", "Title": "F&I Manager", "Email": "harold.ibekwe@example.com"},
    {"EmployeeID": "E3022", "FirstName": "Simone", "LastName": "Aguilar", "Department": "Finance", "Title": "F&I Manager", "Email": "simone.aguilar@example.com"},
    {"EmployeeID": "E3023", "FirstName": "Wesley", "LastName": "Trant", "Department": "Finance", "Title": "BHPH Underwriter", "Email": "wesley.trant@example.com"},
    {"EmployeeID": "E3024", "FirstName": "Carmen", "LastName": "Lugo", "Department": "Finance", "Title": "Collections Specialist", "Email": "carmen.lugo@example.com"},
    {"EmployeeID": "E3025", "FirstName": "Bryce", "LastName": "Dunham", "Department": "Finance", "Title": "Collections Specialist", "Email": "bryce.dunham@example.com"},
    {"EmployeeID": "E3026", "FirstName": "Patricia", "LastName": "Yun", "Department": "Finance", "Title": "Finance Administrator", "Email": "patricia.yun@example.com"},
    {"EmployeeID": "E3027", "FirstName": "Curtis", "LastName": "Boone", "Department": "Service", "Title": "Service Manager", "Email": "curtis.boone@example.com"},
    {"EmployeeID": "E3028", "FirstName": "Yolanda", "LastName": "Price", "Department": "Service", "Title": "Service Advisor", "Email": "yolanda.price@example.com"},
    {"EmployeeID": "E3029", "FirstName": "Miguel", "LastName": "Santoro", "Department": "Service", "Title": "Service Advisor", "Email": "miguel.santoro@example.com"},
    {"EmployeeID": "E3030", "FirstName": "Keisha", "LastName": "Alford", "Department": "Service", "Title": "Service Advisor", "Email": "keisha.alford@example.com"},
    {"EmployeeID": "E3031", "FirstName": "Owen", "LastName": "Radcliffe", "Department": "Service", "Title": "Shop Foreman", "Email": "owen.radcliffe@example.com"},
    {"EmployeeID": "E3032", "FirstName": "Andre", "LastName": "Fontaine", "Department": "Service", "Title": "Master Technician", "Email": "andre.fontaine@example.com"},
    {"EmployeeID": "E3033", "FirstName": "Lucia", "LastName": "Beltran", "Department": "Service", "Title": "Technician", "Email": "lucia.beltran@example.com"},
    {"EmployeeID": "E3034", "FirstName": "Nate", "LastName": "Higgins", "Department": "Service", "Title": "Technician", "Email": "nate.higgins@example.com"},
    {"EmployeeID": "E3035", "FirstName": "Rosalind", "LastName": "Achebe", "Department": "Service", "Title": "Technician", "Email": "rosalind.achebe@example.com"},
    {"EmployeeID": "E3036", "FirstName": "Trey", "LastName": "Simmons", "Department": "Service", "Title": "Apprentice Technician", "Email": "trey.simmons@example.com"},
    {"EmployeeID": "E3037", "FirstName": "Faye", "LastName": "Donahue", "Department": "Service", "Title": "Parts Manager", "Email": "faye.donahue@example.com"},
    {"EmployeeID": "E3038", "FirstName": "Ben", "LastName": "Okafor", "Department": "Service", "Title": "Parts Counterperson", "Email": "ben.okafor@example.com"},
    {"EmployeeID": "E3039", "FirstName": "Colleen", "LastName": "Vasquez", "Department": "Service", "Title": "Parts Counterperson", "Email": "colleen.vasquez@example.com"},
    {"EmployeeID": "E3040", "FirstName": "Felix", "LastName": "Ortega", "Department": "Marketing", "Title": "Marketing Manager", "Email": "felix.ortega@example.com"},
    {"EmployeeID": "E3041", "FirstName": "Aisha", "LastName": "Thornton", "Department": "Marketing", "Title": "Marketing Coordinator", "Email": "aisha.thornton@example.com"},
    {"EmployeeID": "E3042", "FirstName": "Devon", "LastName": "Marsh", "Department": "Marketing", "Title": "Social Media & Content Specialist", "Email": "devon.marsh@example.com"},
    {"EmployeeID": "E3043", "FirstName": "Layla", "LastName": "Fitzgerald", "Department": "Marketing", "Title": "Digital Advertising Specialist", "Email": "layla.fitzgerald@example.com"},
]

FRANCHISE_SALES_IDS = ["E3008", "E3009", "E3010", "E3011", "E3012", "E3013", "E3014"]
BHPH_SALES_IDS = ["E3015", "E3016"]
BDC_SALES_IDS = ["E3017", "E3018"]
SALES_EMPLOYEE_IDS = FRANCHISE_SALES_IDS + BHPH_SALES_IDS + BDC_SALES_IDS

SERVICE_TECHNICIAN_IDS = ["E3032", "E3033", "E3034", "E3035", "E3036"]
SERVICE_ADVISOR_IDS = ["E3028", "E3029", "E3030"]
SERVICE_EMPLOYEE_IDS = SERVICE_TECHNICIAN_IDS

PARTS_COUNTERPERSON_IDS = ["E3038", "E3039"]

FINANCE_STAFF_IDS = ["E3020", "E3021", "E3022", "E3023"]
MARKETING_STAFF_IDS = ["E3040", "E3041", "E3042", "E3043"]


def write_employees():

    path = os.path.join(OUTPUT_DIR, "employees.csv")

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=["EmployeeID", "FirstName", "LastName", "Department", "Title", "Email"]
        )

        writer.writeheader()

        for employee in EMPLOYEES:
            writer.writerow(employee)

    print(f"Wrote {len(EMPLOYEES)} employees -> {path}")


VEHICLE_COUNT = 500
SOLD_FRACTION = 0.62
DEAL_DESK_RESERVE_FRACTION = 0.10
BHPH_LOT_FRACTION = 0.30


def build_vehicles():

    vehicles = []
    bhph_count = int(VEHICLE_COUNT * BHPH_LOT_FRACTION)

    for i in range(1, VEHICLE_COUNT + 1):

        is_bhph = i <= bhph_count

        if is_bhph:

            make, model = random.choice(BHPH_VEHICLES)
            year = random.choice([2015, 2016, 2017, 2018, 2019, 2020])
            mileage = random.randint(58000, 142000)
            condition = "Used"
            base_price = random.randint(7500, 17500)
            lot = "BHPH Used Lot"

        else:

            make, model = random.choice(VEHICLES)
            year = random.choice([2024, 2025])
            used = random.random() < 0.15

            if used:
                mileage = random.randint(8000, 32000)
                condition = "Used"
            else:
                mileage = random.randint(3, 30)
                condition = "New"

            base_price = random.randint(28000, 68000)
            lot = "Franchise New/Used"

        trim = random.choice(TRIMS)
        color = random.choice(COLORS)

        cost_pct = random.uniform(0.70, 0.85) if is_bhph else random.uniform(0.82, 0.92)
        cost = round(base_price * cost_pct, 2)

        vehicles.append({
            "VIN": _vin(make, model, i),
            "Year": str(year),
            "Make": make,
            "Model": model,
            "Trim": trim,
            "Color": color,
            "Mileage": str(mileage),
            "Condition": condition,
            "Price": str(base_price),
            "Cost": str(cost),
            "StockNumber": f"STK{i:05d}",
            "Lot": lot,
            "_is_bhph": is_bhph,
        })

    order = list(range(len(vehicles)))
    random.shuffle(order)

    sold_count = int(VEHICLE_COUNT * SOLD_FRACTION)
    reserved_count = int(VEHICLE_COUNT * DEAL_DESK_RESERVE_FRACTION)

    sold_idx = set(order[:sold_count])
    reserved_idx = set(order[sold_count:sold_count + reserved_count])

    for idx, vehicle in enumerate(vehicles):

        if idx in sold_idx:
            vehicle["DateSold"] = _recency_biased_date(
                date(2024, 11, 1), TODAY, recent_days=30, recent_weight=0.25
            ).isoformat()
            vehicle["_state"] = "sold"
        else:
            vehicle["DateSold"] = ""
            vehicle["_state"] = "deal_desk" if idx in reserved_idx else "in_stock"

    return vehicles


def write_vehicles(vehicles):

    path = os.path.join(OUTPUT_DIR, "vehicles.csv")
    fieldnames = [k for k in vehicles[0].keys() if not k.startswith("_")]

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for vehicle in vehicles:
            writer.writerow({k: v for k, v in vehicle.items() if not k.startswith("_")})

    print(f"Wrote {len(vehicles)} vehicles -> {path}")


CUSTOMER_COUNT = 500
STREET_NAMES = [
    "Main St", "Oak Ave", "Cedar Ln", "Ranch Rd", "Elm St", "Sunset Blvd", "River Rd",
    "Park Pl", "Meadow Dr", "Highland Ave", "Creekside Ln", "Overlook Dr",
]


def _new_customer(i, vin=""):

    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    city, state, zip_prefix = random.choice(CITIES)

    return {
        "CustomerID": f"C{4000 + i}",
        "FirstName": first,
        "LastName": last,
        "Email": f"{first.lower()}.{last.lower()}{i}@example.com",
        "Phone": _phone(),
        "Address": f"{random.randint(100, 9999)} {random.choice(STREET_NAMES)}",
        "City": city,
        "State": state,
        "Zip": f"{zip_prefix}{random.randint(10, 99)}",
        "CreditScore": str(random.randint(520, 820)),
        "Salesperson": random.choice(SALES_EMPLOYEE_IDS),
        "VIN": vin,
    }


def build_customers(vehicles):

    sold_vehicles = [v for v in vehicles if v["_state"] == "sold"]
    deal_desk_vehicles = [v for v in vehicles if v["_state"] == "deal_desk"]

    customers = []
    i = 1

    for vehicle in sold_vehicles:
        customers.append(_new_customer(i, vin=vehicle["VIN"]))
        i += 1

    for vehicle in deal_desk_vehicles:
        customers.append(_new_customer(i, vin=""))
        i += 1

    while len(customers) < CUSTOMER_COUNT:
        customers.append(_new_customer(i, vin=""))
        i += 1

    return customers[:CUSTOMER_COUNT], deal_desk_vehicles


def write_customers(customers):

    path = os.path.join(OUTPUT_DIR, "customers.csv")

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=list(customers[0].keys()))
        writer.writeheader()

        for customer in customers:
            writer.writerow(customer)

    print(f"Wrote {len(customers)} customers -> {path}")


def write_deals(customers):

    path = os.path.join(OUTPUT_DIR, "deals.csv")

    sold_customers = [c for c in customers if c["VIN"]]

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=["CustomerID", "VIN"])
        writer.writeheader()

        for customer in sold_customers:
            writer.writerow({
                "CustomerID": customer["CustomerID"],
                "VIN": customer["VIN"],
            })

    print(f"Wrote {len(sold_customers)} deals -> {path}")


def build_finance(customers, vehicles_by_vin):

    sold_customers = [c for c in customers if c["VIN"]]
    contracts = []

    for i, customer in enumerate(sold_customers, start=1):

        vehicle = vehicles_by_vin[customer["VIN"]]
        sale_price = float(vehicle["Price"]) + random.randint(-1500, 1500)

        credit_score = int(customer["CreditScore"])

        is_bhph = vehicle.get("_is_bhph")

        if is_bhph and random.random() < 0.75:
            apr = round(random.uniform(14.9, 21.9), 2)
            lender_name = IN_HOUSE_LENDER_NAME
        else:

            if credit_score >= 740:
                apr = round(random.uniform(3.9, 5.9), 2)
            elif credit_score >= 660:
                apr = round(random.uniform(5.5, 7.9), 2)
            elif credit_score >= 580:
                apr = round(random.uniform(7.9, 12.9), 2)
            else:
                apr = round(random.uniform(11.9, 18.9), 2)

            make = vehicle["Make"]

            if random.random() < 0.7 and make in LENDERS_BRAND_MATCHED:
                lender_name = LENDERS_BRAND_MATCHED[make]
            else:
                lender_name = random.choice(THIRD_PARTY_LENDERS)

        term_months = random.choice([24, 36, 48, 60, 72, 84]) if is_bhph else random.choice([36, 48, 60, 72, 84])

        down_payment = round(sale_price * random.uniform(0, 0.15), 2)
        amount_financed = round(sale_price - down_payment, 2)

        funding_status = "Pending" if random.random() < 0.06 else "Funded"

        contracts.append({
            "FinanceNumber": f"F{6000 + i}",
            "CustomerID": customer["CustomerID"],
            "VIN": customer["VIN"],
            "LenderName": lender_name,
            "SalePrice": str(round(sale_price, 2)),
            "DownPayment": str(down_payment),
            "AmountFinanced": str(amount_financed),
            "APR": str(apr),
            "TermMonths": str(term_months),
            "MonthlyPayment": str(_monthly_payment(amount_financed, apr, term_months)),
            "FundingStatus": funding_status,
            "ContractDate": vehicle["DateSold"],
        })

    return contracts


def write_finance(contracts):

    path = os.path.join(OUTPUT_DIR, "finance.csv")

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=list(contracts[0].keys()))
        writer.writeheader()

        for contract in contracts:
            writer.writerow(contract)

    print(f"Wrote {len(contracts)} finance contracts -> {path}")


def build_service(customers, vehicles_by_vin):

    buyer_customers = [c for c in customers if c["VIN"]]
    service_only_customers = [c for c in customers if not c["VIN"]]

    serviced_buyers = random.sample(buyer_customers, k=int(len(buyer_customers) * 0.28))

    serviced_only = random.sample(
        service_only_customers, k=int(len(service_only_customers) * 0.85)
    )

    records = []
    counter = 1

    def _add_record(customer, vin, earliest, latest):

        nonlocal counter

        service_date = _recency_biased_date(earliest, latest, recent_days=30, recent_weight=0.3)

        description = random.choice(SERVICE_DESCRIPTIONS)
        is_recall = "Recall" in description

        cost = 0.0 if is_recall else round(random.uniform(29.99, 899.99), 2)

        if is_recall:
            pay_type = "Warranty"
            parts_cost = 0.0
            labor_hours = round(random.uniform(0.3, 1.2), 1)
        elif random.random() < 0.05:
            pay_type = "Internal"
            parts_cost = round(cost * random.uniform(0.3, 0.45), 2)
            labor_hours = round(random.uniform(0.5, 4.5), 1)
        else:
            pay_type = "Customer Pay"
            parts_cost = round(cost * random.uniform(0.3, 0.45), 2)
            labor_hours = round(random.uniform(0.5, 4.5), 1)

        vehicle = vehicles_by_vin.get(vin) if vin else None
        base_mileage = int(vehicle["Mileage"]) if vehicle else random.randint(20000, 90000)

        records.append({
            "ServiceNumber": f"S{7000 + counter}",
            "CustomerID": customer["CustomerID"],
            "VIN": vin or "",
            "Description": description,
            "ServiceDate": service_date.isoformat(),
            "Mileage": str(base_mileage + random.randint(500, 20000)),
            "Cost": str(cost),
            "PartsCost": str(parts_cost),
            "LaborHours": str(labor_hours),
            "PayType": pay_type,
            "Status": "Completed",
            "Technician": random.choice(SERVICE_TECHNICIAN_IDS),
        })

        counter += 1

    for customer in serviced_buyers:

        vehicle = vehicles_by_vin[customer["VIN"]]
        sold_date = date.fromisoformat(vehicle["DateSold"])
        earliest_service = sold_date + timedelta(days=14)

        if earliest_service >= TODAY:
            continue

        visits = random.choices([1, 2, 3], weights=[60, 30, 10])[0]

        for _ in range(visits):
            _add_record(customer, customer["VIN"], earliest_service, TODAY)

    for customer in serviced_only:

        visits = random.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0]

        for _ in range(visits):
            _add_record(customer, "", TODAY - timedelta(days=540), TODAY)

    return records


def write_service(records):

    path = os.path.join(OUTPUT_DIR, "service.csv")

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
        writer.writeheader()

        for record in records:
            writer.writerow(record)

    print(f"Wrote {len(records)} service records -> {path}")


LEAD_COUNT = 1000


def build_leads():

    leads = []

    for i in range(1, LEAD_COUNT + 1):

        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        city, state, _ = random.choice(CITIES)

        status = random.choices(LEAD_STATUSES, weights=LEAD_STATUS_WEIGHTS)[0]
        source = random.choices(LEAD_SOURCES, weights=LEAD_SOURCE_WEIGHTS)[0]

        leads.append({
            "LeadID": f"L{8000 + i}",
            "FirstName": first,
            "LastName": last,
            "Email": f"{first.lower()}.{last.lower()}.lead{i}@example.com",
            "Phone": _phone(),
            "City": city,
            "State": state,
            "Source": source,
            "Status": status,
            "AssignedSalesperson": random.choice(SALES_EMPLOYEE_IDS),
            "CreatedDate": _recency_biased_date(
                TODAY - timedelta(days=270), TODAY, recent_days=14, recent_weight=0.2
            ).isoformat(),
            "VIN": "",
        })

    return leads


def write_leads(leads):

    path = os.path.join(OUTPUT_DIR, "leads.csv")

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=list(leads[0].keys()))
        writer.writeheader()

        for lead in leads:
            writer.writerow(lead)

    print(f"Wrote {len(leads)} leads -> {path}")


def build_parts(count=300):

    parts = []

    for i in range(1, count + 1):

        name, category = random.choice(PART_CATALOG)

        unit_cost = round(random.uniform(4.0, 320.0), 2)
        markup = random.uniform(1.4, 2.2)
        list_price = round(unit_cost * markup, 2)

        quantity_on_hand = random.randint(0, 45)

        received_date = _random_date(
            TODAY - timedelta(days=420), TODAY
        )

        velocity = random.choices(
            ["fast", "medium", "slow"],
            weights=[0.3, 0.45, 0.25]
        )[0]

        parts.append({
            "PartNumber": f"PN-{10000 + i}",
            "Description": name,
            "Category": category,
            "QuantityOnHand": str(quantity_on_hand),
            "UnitCost": str(unit_cost),
            "ListPrice": str(list_price),
            "ReceivedDate": received_date.isoformat(),
            "_velocity": velocity,
        })

    return parts


def write_parts(parts):

    path = os.path.join(OUTPUT_DIR, "parts.csv")
    fieldnames = [k for k in parts[0].keys() if not k.startswith("_")]

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for part in parts:
            writer.writerow({k: v for k, v in part.items() if not k.startswith("_")})

    print(f"Wrote {len(parts)} parts -> {path}")


def build_part_sales(parts, count=1800):

    weight_by_velocity = {"fast": 6, "medium": 2, "slow": 0.3}
    weights = [weight_by_velocity[p["_velocity"]] for p in parts]

    sales = []

    for i in range(1, count + 1):

        part = random.choices(parts, weights=weights, k=1)[0]

        quantity_sold = random.randint(1, 4)
        unit_cost = float(part["UnitCost"])
        list_price = float(part["ListPrice"])

        discount = random.uniform(0.85, 1.0)
        sale_price = round(list_price * quantity_sold * discount, 2)
        cost = round(unit_cost * quantity_sold, 2)
        gross_profit = round(sale_price - cost, 2)

        customer_type = random.choices(
            PART_SALE_CUSTOMER_TYPES,
            weights=[0.55, 0.2, 0.1, 0.15]
        )[0]

        window_days = 90 if part["_velocity"] != "slow" else 150
        sale_date = _recency_biased_date(
            TODAY - timedelta(days=window_days), TODAY, recent_days=30, recent_weight=0.3
        )

        sales.append({
            "SaleNumber": f"PS-{30000 + i}",
            "PartNumber": part["PartNumber"],
            "SaleDate": sale_date.isoformat(),
            "QuantitySold": str(quantity_sold),
            "SalePrice": str(sale_price),
            "Cost": str(cost),
            "GrossProfit": str(gross_profit),
            "CustomerType": customer_type,
            "Counterperson": random.choice(PARTS_COUNTERPERSON_IDS),
        })

    return sales


def write_part_sales(sales):

    path = os.path.join(OUTPUT_DIR, "part_sales.csv")

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=list(sales[0].keys()))
        writer.writeheader()

        for sale in sales:
            writer.writerow(sale)

    print(f"Wrote {len(sales)} part sales -> {path}")


def write_deal_desk_pairs(deal_desk_vehicles, customers):

    reserved_customers = [c for c in customers if not c["VIN"]][: len(deal_desk_vehicles)]

    path = os.path.join(OUTPUT_DIR, "deal_desk_pairs.csv")

    with open(path, "w", newline="", encoding="utf-8") as file:

        writer = csv.DictWriter(file, fieldnames=["CustomerID", "VIN"])
        writer.writeheader()

        pairs = list(zip(reserved_customers, deal_desk_vehicles))

        for customer, vehicle in pairs:
            writer.writerow({"CustomerID": customer["CustomerID"], "VIN": vehicle["VIN"]})

    print(f"Wrote {len(pairs)} Deal Desk reservation pairs -> {path}")

    return pairs


def main():

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    write_employees()

    vehicles = build_vehicles()
    write_vehicles(vehicles)

    customers, deal_desk_vehicles = build_customers(vehicles)
    write_customers(customers)

    write_deals(customers)

    vehicles_by_vin = {v["VIN"]: v for v in vehicles}

    finance = build_finance(customers, vehicles_by_vin)
    write_finance(finance)

    service = build_service(customers, vehicles_by_vin)
    write_service(service)

    leads = build_leads()
    write_leads(leads)

    parts = build_parts()
    write_parts(parts)

    part_sales = build_part_sales(parts)
    write_part_sales(part_sales)

    write_deal_desk_pairs(deal_desk_vehicles, customers)

    print("\nDone. Run `python run_seed_import.py` next to load these into storage/graph.json.")


if __name__ == "__main__":
    main()

