# Lead Lifecycle

INTERESTED_IN = "INTERESTED_IN"

BECAME = "BECAME"


# Sales & Ownership

PURCHASED = "PURCHASED"

OWNS = "OWNS"

TRADED_IN = "TRADED_IN"


# Finance

FINANCED_BY = "FINANCED_BY"

FUNDED_BY = "FUNDED_BY"

COVERS = "COVERS"


# Service

HAS_SERVICE_RECORD = "HAS_SERVICE_RECORD"

AUTHORIZED = "AUTHORIZED"

INCLUDES_SERVICE_PLAN = "INCLUDES_SERVICE_PLAN"


# Media & Documents

HAS_DOCUMENT = "HAS_DOCUMENT"

HAS_IMAGE = "HAS_IMAGE"


# Marketing

PARTICIPATED_IN_CAMPAIGN = "PARTICIPATED_IN_CAMPAIGN"

RECEIVED_CAMPAIGN = "RECEIVED_CAMPAIGN"

GENERATED_LEAD = "GENERATED_LEAD"


# Employee Operations

ASSIGNED_TO = "ASSIGNED_TO"

MANAGED_BY = "MANAGED_BY"


# Inventory

LOCATED_AT = "LOCATED_AT"

PART_OF_INVENTORY = "PART_OF_INVENTORY"


# Parts department (Department Intelligence, session 35)

SOLD_PART = "SOLD_PART"       # PartSale -> Part

SOLD_BY = "SOLD_BY"           # PartSale -> Employee (counterperson)


# Department job-workflow engine (session 53)

TRACKS = "TRACKS"             # WorkflowInstance -> whatever entity the job is
                               # actually about (Vehicle, Deal, etc.), optional


# Graph exploration / knowledge linking (session 76 fourth follow-up -- Sam: "everything
# that's created in workspace, referenced in chats, group messages as well as in the
# dashes -- all of that knowledge association needs to be interconnected into the
# graph"). Real relationships, not just client-side text links, so traversal works in
# both directions (Customer -> messages that mentioned them, not just message -> Customer
# link rendering). See core/entity_mentions.py.

MENTIONS = "MENTIONS"                 # Message -> an entity referenced by ID in its
                                       # content

REFERENCES = "REFERENCES"             # KnowledgePin -> the real entity its ref_id
                                       # points at (only created when ref_id actually
                                       # resolves to a graph entity -- see
                                       # core/knowledge_pins.py's create_pin)
