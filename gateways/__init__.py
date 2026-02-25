import glob
import importlib
import os
import inspect

async def register_gateways(bot):
    """Automatically register all gateway modules"""
    # Get the directory containing the gateways
    gateway_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Find all Python files in the directory except __init__.py
    gateway_files = glob.glob(os.path.join(gateway_dir, "*.py"))
    gateway_files = [f for f in gateway_files if not f.endswith("__init__.py")]
    
    registration_funcs = {}

    for file_path in gateway_files:
        try:
            # Get module name from file path
            module_name = os.path.splitext(os.path.basename(file_path))[0]
            # Import the module
            module = importlib.import_module(f".{module_name}", package="gateways")
            
            # Find registration function in module
            for name, obj in inspect.getmembers(module):
                if (inspect.iscoroutinefunction(obj) and 
                    name.startswith("register_")):
                    # name.endswith("_gateway"))
                    registration_funcs[module_name] = obj
        except Exception as e:
            print(f"Failed to load gateway {module_name}: {e}")
    
    # Register all found gateways
    for module_name, func in registration_funcs.items():
        try:
            await func(bot)
            print(f"Registered gateway: {module_name}")
        except Exception as e:
            print(f"Failed to register gateway {module_name}: {e}")
    print("Gateway registration complete")