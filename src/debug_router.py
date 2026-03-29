# debug_router.py - Run this to test the router directly

from fastapi import FastAPI
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_router():
    """Test router inclusion directly"""
    
    # Create a minimal FastAPI app
    app = FastAPI()
    
    # Test importing the router
    try:
        from routes.prediction import prediction_router
        print(f"✅ Router imported successfully")
        print(f"✅ Router prefix: {prediction_router.prefix}")
        print(f"✅ Router tags: {prediction_router.tags}")
        print(f"✅ Number of routes: {len(prediction_router.routes)}")
        
        # Show individual routes
        print("\n📋 Individual routes in prediction_router:")
        for route in prediction_router.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                print(f"  {route.methods} {route.path}")
        
        # Include the router in the app
        app.include_router(prediction_router)
        print(f"✅ Router included successfully")
        
        # Show all routes in the app
        print(f"\n📋 All routes in app after including prediction_router:")
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                print(f"  {route.methods} {route.path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_router()