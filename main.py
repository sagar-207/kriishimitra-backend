from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import motor.motor_asyncio
import os
from bson import ObjectId

app = FastAPI(title="KriishiMitra API", version="1.0.0")

# ─── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── MongoDB Atlas Connection ────────────────────────────────────────────────
MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb+srv://sagar_admin:sagar123@cluster0.nfebz23.mongodb.net/?appName=Cluster0"
)

client = motor.motor_asyncio.AsyncIOMotorClient("mongodb+srv://sagar_admin:sagar123@cluster0.nfebz23.mongodb.net/?appName=Cluster0")
db = client.kriishimitra

users_col     = db["users"]
products_col  = db["products"]
orders_col    = db["orders"]

# ─── Helpers ─────────────────────────────────────────────────────────────────
def fix_id(doc):
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ─── Crop Suggestion Engine ───────────────────────────────────────────────────
CROP_SUGGESTIONS = {
    "tomato":     {"demand": "High", "price_range": "₹30–₹50/kg",  "tip": "Sell early morning for best price"},
    "potato":     {"demand": "Very High", "price_range": "₹15–₹25/kg", "tip": "Store in cool, dry place"},
    "onion":      {"demand": "High", "price_range": "₹20–₹40/kg",  "tip": "Market demand spikes in summer"},
    "wheat":      {"demand": "Stable", "price_range": "₹20–₹30/kg", "tip": "Government MSP available"},
    "rice":       {"demand": "Stable", "price_range": "₹25–₹45/kg", "tip": "Basmati gets premium price"},
    "maize":      {"demand": "Growing", "price_range": "₹18–₹28/kg", "tip": "Good for poultry feed market"},
    "carrot":     {"demand": "Medium", "price_range": "₹25–₹40/kg", "tip": "Winter crop, sell Oct–Feb"},
    "spinach":    {"demand": "High", "price_range": "₹20–₹35/kg",  "tip": "Short shelf life, sell fast"},
    "brinjal":    {"demand": "Medium", "price_range": "₹15–₹30/kg", "tip": "Consistent demand year-round"},
    "cauliflower":{"demand": "High", "price_range": "₹20–₹40/kg",  "tip": "Best price in winter"},
    "cabbage":    {"demand": "Medium", "price_range": "₹10–₹20/kg", "tip": "Bulk buyers available"},
    "mango":      {"demand": "Very High", "price_range": "₹60–₹120/kg","tip": "Alphonso fetches premium"},
    "banana":     {"demand": "High", "price_range": "₹25–₹40/kg",  "tip": "Year-round demand"},
    "grapes":     {"demand": "High", "price_range": "₹50–₹100/kg", "tip": "Export quality gets 2x price"},
    "sugarcane":  {"demand": "Stable", "price_range": "₹300–₹350/quintal","tip": "Sell to nearby mills"},
    "soybean":    {"demand": "Growing", "price_range": "₹45–₹55/kg", "tip": "Export demand rising"},
    "cotton":     {"demand": "Stable", "price_range": "₹60–₹70/kg", "tip": "Government procurement available"},
    "turmeric":   {"demand": "High", "price_range": "₹70–₹120/kg", "tip": "Organic gets 40% premium"},
    "chilli":     {"demand": "High", "price_range": "₹80–₹150/kg", "tip": "Dry red chilli exports well"},
    "garlic":     {"demand": "High", "price_range": "₹40–₹80/kg",  "tip": "Long shelf life advantage"},
}

# ─── Pydantic Models ──────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str
    phone: str
    password: str
    role: str  # "farmer" | "customer"
    location: Optional[str] = ""

class LoginRequest(BaseModel):
    phone: str
    password: str

class ProductRequest(BaseModel):
    farmer_id: str
    farmer_name: str
    crop_name: str
    price: float
    quantity: float
    unit: Optional[str] = "kg"
    description: Optional[str] = ""
    location: Optional[str] = ""

class BuyRequest(BaseModel):
    customer_id: str
    customer_name: str
    product_id: str
    quantity: float


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "KriishiMitra API v1.0 🌾", "status": "running"}


@app.post("/register")
async def register(req: RegisterRequest):
    existing = await users_col.find_one({"phone": req.phone})
    if existing:
        raise HTTPException(status_code=400, detail="Phone already registered")

    user = {
        "name": req.name,
        "phone": req.phone,
        "password": req.password,  # In prod: hash with bcrypt
        "role": req.role,
        "location": req.location,
        "created_at": datetime.utcnow().isoformat(),
    }
    result = await users_col.insert_one(user)
    user["_id"] = str(result.inserted_id)
    del user["password"]
    return {"success": True, "user": user}


@app.post("/login")
async def login(req: LoginRequest):
    user = await users_col.find_one({"phone": req.phone, "password": req.password})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid phone or password")
    user = fix_id(user)
    del user["password"]
    return {"success": True, "user": user}


@app.post("/add-product")
async def add_product(req: ProductRequest):
    product = {
        "farmer_id": req.farmer_id,
        "farmer_name": req.farmer_name,
        "crop_name": req.crop_name,
        "price": req.price,
        "quantity": req.quantity,
        "available_quantity": req.quantity,
        "unit": req.unit,
        "description": req.description,
        "location": req.location,
        "status": "available",
        "created_at": datetime.utcnow().isoformat(),
    }
    result = await products_col.insert_one(product)
    product["_id"] = str(result.inserted_id)
    return {"success": True, "product": product}


@app.get("/products")
async def get_products(search: Optional[str] = None, farmer_id: Optional[str] = None):
    query = {"status": "available", "available_quantity": {"$gt": 0}}
    if search:
        query["crop_name"] = {"$regex": search, "$options": "i"}
    if farmer_id:
        query = {"farmer_id": farmer_id}
        del query["status"]
        del query["available_quantity"]

    cursor = products_col.find(query).sort("created_at", -1)
    products = []
    async for doc in cursor:
        products.append(fix_id(doc))
    return {"success": True, "products": products}


@app.post("/buy")
async def buy_product(req: BuyRequest):
    product = await products_col.find_one({"_id": ObjectId(req.product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product["available_quantity"] < req.quantity:
        raise HTTPException(status_code=400, detail="Insufficient quantity available")

    total_price = product["price"] * req.quantity

    order = {
        "customer_id": req.customer_id,
        "customer_name": req.customer_name,
        "farmer_id": product["farmer_id"],
        "farmer_name": product["farmer_name"],
        "product_id": req.product_id,
        "crop_name": product["crop_name"],
        "quantity": req.quantity,
        "unit": product["unit"],
        "price_per_unit": product["price"],
        "total_price": total_price,
        "status": "pending",  # pending | in_transit | delivered
        "created_at": datetime.utcnow().isoformat(),
    }
    result = await orders_col.insert_one(order)
    order["_id"] = str(result.inserted_id)

    # Update available quantity
    new_qty = product["available_quantity"] - req.quantity
    update_data = {"available_quantity": new_qty}
    if new_qty <= 0:
        update_data["status"] = "sold_out"
    await products_col.update_one({"_id": ObjectId(req.product_id)}, {"$set": update_data})

    return {"success": True, "order": order}


@app.get("/orders")
async def get_orders(farmer_id: Optional[str] = None, customer_id: Optional[str] = None):
    query = {}
    if farmer_id:
        query["farmer_id"] = farmer_id
    if customer_id:
        query["customer_id"] = customer_id

    cursor = orders_col.find(query).sort("created_at", -1)
    orders = []
    async for doc in cursor:
        orders.append(fix_id(doc))
    return {"success": True, "orders": orders}


@app.patch("/orders/{order_id}/status")
async def update_order_status(order_id: str, status: str):
    valid = ["pending", "in_transit", "delivered"]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of {valid}")
    await orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": status}})
    return {"success": True, "message": f"Order status updated to {status}"}


@app.get("/crop-suggestion")
async def crop_suggestion(crop: str):
    key = crop.lower().strip()
    # Try exact match first
    if key in CROP_SUGGESTIONS:
        return {"success": True, "found": True, "crop": crop, **CROP_SUGGESTIONS[key]}
    # Try partial match
    for k, v in CROP_SUGGESTIONS.items():
        if k in key or key in k:
            return {"success": True, "found": True, "crop": crop, **v}
    return {"success": True, "found": False, "crop": crop,
            "demand": "Unknown", "price_range": "Market rate", "tip": "Check local mandi prices"}


@app.get("/farmer-stats/{farmer_id}")
async def farmer_stats(farmer_id: str):
    # Count products
    total_products = await products_col.count_documents({"farmer_id": farmer_id})

    # Count orders & revenue
    total_orders = await orders_col.count_documents({"farmer_id": farmer_id})
    pending_orders = await orders_col.count_documents({"farmer_id": farmer_id, "status": "pending"})

    # Revenue
    revenue = 0
    async for order in orders_col.find({"farmer_id": farmer_id, "status": "delivered"}):
        revenue += order.get("total_price", 0)

    return {
        "success": True,
        "total_products": total_products,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "total_revenue": revenue,
    }
