class AmbiguousVehicleIdentity(ValueError):
    """No automatic choice is safe when an unindexed VIN has multiple targets."""


class EntityRegistry:

    def __init__(self, ledger=None):

        self._ledger = ledger
        self.vehicle_vins = {}
        self.customer_ids = {}
        self.lead_ids = {}

        self.finance_ids = {}
        self.lenders = {}
        self.employee_ids = {}
        self.part_numbers = {}

    # ------------------
    # Vehicles
    # ------------------

    def register_vehicle(self, vin, entity_id):
        self.vehicle_vins[vin] = entity_id

    def find_vehicle(self, vin, *, require_unique=False):
        registered = self.vehicle_vins.get(vin)
        if registered or self._ledger is None or not isinstance(vin, str) or not vin.strip():
            return registered
        # Bridge and graph reloads need not mutate this legacy in-memory index.
        # VIN is a vehicle identity, unlike vendor-scoped customer/lead IDs.
        normalized = vin.strip().upper()
        with self._ledger.persistence_guard():
            matches = [entity.id for entity in list(self._ledger.get_all().values())
                       if entity.entity_type == "Vehicle" and
                       entity.attributes.get("workspace_id", self._ledger.tenant.workspace_id) == self._ledger.tenant.workspace_id and
                       any(isinstance(value, str) and value.strip().upper() == normalized
                           for value in (entity.attributes.get("VIN"), entity.attributes.get("vin")))]
        if len(matches) > 1:
            if require_unique:
                raise AmbiguousVehicleIdentity("VIN matches multiple vehicles; review their identities before continuing")
            return None  # Existing optional relationship callers must not guess.
        return matches[0] if matches else None

    # ------------------
    # Customers
    # ------------------

    def register_customer(
        self,
        customer_id,
        entity_id
    ):
        self.customer_ids[customer_id] = entity_id

    def find_customer(self, customer_id):
        return self.customer_ids.get(customer_id)

    # ------------------
    # Leads
    # ------------------

    def register_lead(
        self,
        lead_id,
        entity_id
    ):
        self.lead_ids[lead_id] = entity_id

    def find_lead(self, lead_id):
        return self.lead_ids.get(lead_id)

    # ------------------
    # Finance Contracts
    # ------------------

    def register_finance(
        self,
        finance_number,
        entity_id
    ):
        self.finance_ids[finance_number] = entity_id

    def find_finance(self, finance_number):
        return self.finance_ids.get(finance_number)

    # ------------------
    # Lenders
    # ------------------

    def register_lender(
        self,
        lender_name,
        entity_id
    ):
        self.lenders[lender_name] = entity_id

    def find_lender(self, lender_name):
        return self.lenders.get(lender_name)

    # ------------------
    # Employees
    # ------------------

    def register_employee(self, employee_id_key, entity_id):
        self.employee_ids[employee_id_key] = entity_id

    def find_employee(self, employee_id_key):
        return self.employee_ids.get(employee_id_key)

    # ------------------
    # Parts (Department Intelligence, session 35)
    # ------------------

    def register_part(self, part_number, entity_id):
        self.part_numbers[part_number] = entity_id

    def find_part(self, part_number):
        return self.part_numbers.get(part_number)
