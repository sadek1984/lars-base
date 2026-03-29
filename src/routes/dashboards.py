from fastapi import APIRouter, Depends, HTTPException, Query, Request
from datetime import datetime
import logging
import pandas as pd
import io
from fastapi.responses import StreamingResponse

# Correctly import the service from its own file
from services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

# The prefix is just /dashboards. The /api/v1 part should be added in your main.py
dashboard_router = APIRouter(
    prefix="/dashboards",
    tags=["Power BI Dashboards"]
)

# --- FastAPI Dependency Injection ---
def get_dashboard_service(request: Request) -> DashboardService:
    """
    Dependency that creates and returns an instance of DashboardService.
    It can access the app state (like a db_client) if needed.
    """
    db_client = request.app.db_client if hasattr(request.app, 'db_client') else None
    return DashboardService(db_client=db_client)


@dashboard_router.get("/executive", summary="Get Executive Dashboard Data")
async def get_executive_dashboard(
    service: DashboardService = Depends(get_dashboard_service)
):
    """
    Provides high-level KPIs for executive oversight, including overall
    compliance rates, risk distribution, and top contaminated products.
    """
    logger.info("'/executive' endpoint called.")
    try:
        result = await service.get_executive_dashboard()
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500, 
                detail=result.get("error", "Failed to generate dashboard data.")
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Unexpected error in /executive endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

@dashboard_router.get("/laboratory", summary="Get Laboratory Dashboard Data")
async def get_laboratory_dashboard(
    service: DashboardService = Depends(get_dashboard_service)
):
    """
    Provides operational metrics for laboratory management, such as daily
    processing stats, alerts, and workload distribution.
    """
    logger.info("'/laboratory' endpoint called.")
    try:
        result = await service.get_laboratory_dashboard()
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate laboratory dashboard data.")
            )
            
        return result

    except Exception as e:
        logger.error(f"Unexpected error in /laboratory endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

@dashboard_router.get("/regulatory", summary="Get Regulatory Dashboard Data")
async def get_regulatory_dashboard(
    service: DashboardService = Depends(get_dashboard_service)
):
    """
    Provides compliance metrics for regulatory reporting, including
    violation tracking and compliance by product type.
    """
    logger.info("'/regulatory' endpoint called.")
    try:
        result = await service.get_regulatory_dashboard()
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate regulatory dashboard data.")
            )
            
        return result

    except Exception as e:
        logger.error(f"Unexpected error in /regulatory endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

@dashboard_router.get("/data/flat", summary="Get Flattened Data for Power BI")
async def get_flat_data_for_powerbi(
    service: DashboardService = Depends(get_dashboard_service)
):
    """
    Provides a combined, flattened JSON object containing data from all dashboards,
    optimized for easy import into Power BI.
    """
    logger.info("'/data/flat' endpoint called.")
    try:
        # Correctly call the methods from DashboardService
        executive_result = await service.get_executive_dashboard()
        laboratory_result = await service.get_laboratory_dashboard()
        regulatory_result = await service.get_regulatory_dashboard()

        if not all([executive_result.get("success"), laboratory_result.get("success"), regulatory_result.get("success")]):
            raise HTTPException(status_code=500, detail="Failed to generate data for one or more dashboards.")

        # Combine the data from all dashboards into a flat structure
        flat_data = {
            "executive_summary": executive_result.get("data", {}).get("summary", {}),
            "risk_distribution": executive_result.get("data", {}).get("risk_distribution", {}),
            "laboratory_summary": laboratory_result.get("data", {}).get("summary", {}),
            "regulatory_summary": regulatory_result.get("data", {}).get("compliance_summary", {})
        }

        return {
            "success": True,
            "dashboard_type": "flat",
            "data": flat_data,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Unexpected error in /data/flat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred while generating flat data.")


@dashboard_router.get("/executive/export", summary="Export Executive Data as Excel")
async def export_executive_data(
    service: DashboardService = Depends(get_dashboard_service)
):
    """
    Exports key data from the executive dashboard into an Excel file
    with multiple sheets for offline analysis.
    """
    logger.info("'/executive/export' endpoint called.")
    try:
        # Correctly call the method from DashboardService
        result = await service.get_executive_dashboard()
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to generate data for export."))
        
        data = result.get("data", {})
        
        # Create DataFrames for each part of the dashboard
        summary_df = pd.DataFrame([data.get("summary", {})])
        risk_df = pd.DataFrame(list(data.get("risk_distribution", {}).items()), columns=['Risk Level', 'Count'])
        veg_df = pd.DataFrame(list(data.get("top_contaminated_vegetables", {}).items()), columns=['Vegetable', 'Count'])
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            risk_df.to_excel(writer, sheet_name='Risk Distribution', index=False)
            veg_df.to_excel(writer, sheet_name='Contaminated Vegetables', index=False)
        
        output.seek(0)
        filename = f"executive_dashboard_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Unexpected error in /executive/export endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred during export.")

@dashboard_router.get("/health", summary="Health Check")
async def dashboard_health_check():
    """Checks if the dashboard service router is operational."""
    return {
        "status": "healthy",
        "service": "powerbi_dashboards",
        "timestamp": datetime.now().isoformat()
    }