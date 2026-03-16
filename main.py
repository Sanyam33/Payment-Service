from fastapi import FastAPI
from db import engine, Base
import router
from router import async_client

Base.metadata.create_all(bind=engine)
app = FastAPI()

app.include_router(router.payment_router)

@app.get("/")
def root():
    return {"message": "Welcome to the Payment Gateway API"}

@app.get("/help")
def help():
    return{
        "endpoints": {
            "create": "POST /api/v1/transactions/create"
        },
        "example_payload":{
            "amount": 777,
            "order_id": 30,
            "payment_method": "stripe",
            "type": "credit",
            "user_id": "9f4c9f25-9d5c-4fa1-9a7d-123456789abc"
        }
    }

@app.on_event("shutdown")
async def shutdown_event():
    await async_client.aclose()

# from fastapi import FastAPI, HTTPException
# import httpx

# app = FastAPI()

# WISE_API_TOKEN = "your_sandbox_token_here"
# WISE_BASE_URL = "https://api.wise-sandbox.com"
# PROFILE_ID = "your_profile_id_here" # Obtained from Step 1

# headers = {
#     "Authorization": f"Bearer {WISE_API_TOKEN}",
#     "Content-Type": "application/json"
# }

# @app.get("/wallet/balances")
# async def get_wise_balances():
#     """
#     Fetches all active balances for the business profile.
#     """
#     url = f"{WISE_BASE_URL}/v4/profiles/{PROFILE_ID}/balances?types=STANDARD"
    
#     async with httpx.AsyncClient() as client:
#         response = await client.get(url, headers=headers)
        
#         if response.status_code != 200:
#             raise HTTPException(status_code=response.status_code, detail=response.text)
            
#         return response.json()