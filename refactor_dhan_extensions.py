import os
import glob

replacements = [
    ("from brokers.dhan.domain import", "from brokers.adapters.dhan.extensions.models import"),
    ("from brokers.dhan.exceptions import", "from brokers.domain.exceptions import"),
    ("from brokers.dhan.exceptions", "from brokers.domain.exceptions"),
    ("from brokers.dhan.http_client import", "from brokers.adapters.dhan.http import"),
    ("from brokers.dhan.identity import", "from brokers.adapters.dhan.identity import"),
    ("from brokers.dhan.invariants import", "from brokers.adapters.dhan.invariants import"),
    ("from domain.entities import", "from brokers.domain.entities import"),
    ("from domain.utils.price import", "from brokers.utils.price import"),
    ("domain.entities.instrument.Instrument", "brokers.ports.instruments.InstrumentInfo"),
    ("SuperOrderError", "BrokerError"),
    ("ForeverOrderError", "BrokerError"),
    ("DhanIdentityProvider", "DhanInstrumentResolver"),
    ("coerce_identity_provider", ""),
    ("assert_dhan_payload", "assert_valid_dhan_payload"),
    ("from brokers.adapters.dhan.identity import DhanInstrumentResolver, ", "from brokers.adapters.dhan.identity import DhanInstrumentResolver\n")
]

for filepath in glob.glob("brokers/adapters/dhan/extensions/*.py"):
    with open(filepath, "r") as f:
        content = f.read()
    
    for old, new in replacements:
        content = content.replace(old, new)
        
    if "coerce_identity_provider" not in content and "DhanInstrumentResolver | object" in content:
         content = content.replace("DhanInstrumentResolver | object", "DhanInstrumentResolver")
         
    # Fix the init in adapters
    content = content.replace("self._identity = coerce_identity_provider(identity)", "self._resolver = identity")
    content = content.replace("self._identity", "self._resolver")
    content = content.replace("self._resolver = self._resolver.resolver", "")

    # Fix models.py specific issues
    if "models.py" in filepath:
        content = content.replace("import domain.entities.instrument", "from brokers.ports.instruments import InstrumentInfo")
        content = content.replace("domain_instrument: 'domain.entities.instrument.Instrument'", "domain_instrument: InstrumentInfo")
        
    with open(filepath, "w") as f:
        f.write(content)

print("Refactoring complete.")
