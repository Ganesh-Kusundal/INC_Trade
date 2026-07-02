import os
import sys

# Setup path for archive package
sys.path.append(os.path.abspath("archive"))

try:
    from infrastructure.di import ServiceLocator
    from config.schema import AppConfig
    
    print("=== Configuration Schema ===")
    print(AppConfig.model_fields.keys())
    
    print("\n=== DI Container Locator ===")
    # Print out whatever we can from ServiceLocator or di modules
    print(dir(ServiceLocator))
    
    # Try to initialize config
    from config import ConfigLoader
    try:
        cfg = ConfigLoader().load()
        print("Config successfully loaded!")
    except Exception as e:
        print(f"Config load failed: {e}")
        
    print("\n=== Lifecycle ===")
    import infrastructure.lifecycle
    print(dir(infrastructure.lifecycle))
except ImportError as e:
    print(f"Import error: {e}")
except Exception as e:
    print(f"Error: {e}")
