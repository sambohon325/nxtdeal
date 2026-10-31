from core.ledger import DealerLedger
from core.registry import EntityRegistry
from core.id_generator import IDGenerator

ledger = DealerLedger()
registry = EntityRegistry(ledger)
id_generator = IDGenerator()
