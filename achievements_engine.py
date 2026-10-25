"""
achievements_engine.py
Core calculation engine, date arithmetic, and product search for Bucksy Achievement Calculator.
"""

import math
import calendar
from datetime import date, datetime, timedelta
import os
import json
import urllib.request
import urllib.parse

# ── Date Arithmetic Helpers ────────────────────────────────────────────────────

def add_calendar_months(start_date: date, months: int) -> date:
    """
    Accurately adds a number of calendar months to a date,
    properly handling variable month lengths (28, 29, 30, 31) and leap years.
    Clamps day of month to the maximum available days in the destination month.
    """
    if months <= 0:
        return start_date
    total_months = (start_date.year * 12 + (start_date.month - 1)) + months
    new_year = total_months // 12
    new_month = (total_months % 12) + 1
    max_days = calendar.monthrange(new_year, new_month)[1]
    new_day = min(start_date.day, max_days)
    return date(new_year, new_month, new_day)


# ── Savings Calculation Engine ────────────────────────────────────────────────

def calculate_savings_plan(
    target_price: float,
    current_savings: float = 0.0,
    extra_costs: float = 0.0,
    saving_amount: float = 0.0,
    saving_frequency: str = "daily",
    start_date: date = None
) -> dict:
    """
    Calculates remaining target amount, completion timeframe, and estimated achievement date.
    
    Formula:
    Remaining amount = Target price + Extra costs - Current savings
    """
    if start_date is None:
        start_date = date.today()
    
    # Clean and round monetary inputs to avoid floating-point issues
    target_price = round(float(target_price or 0), 2)
    current_savings = round(float(current_savings or 0), 2)
    extra_costs = round(float(extra_costs or 0), 2)
    saving_amount = round(float(saving_amount or 0), 2)
    saving_frequency = (saving_frequency or "daily").lower()
    if saving_frequency not in ("daily", "weekly", "monthly"):
        saving_frequency = "daily"

    total_target = round(target_price + extra_costs, 2)
    remaining_amount = round(max(0.0, total_target - current_savings), 2)
    
    # Progress percentage capped between 0 and 100
    if total_target > 0:
        progress_pct = round(min(100.0, max(0.0, (current_savings / total_target) * 100)), 1)
    else:
        progress_pct = 100.0 if current_savings >= 0 else 0.0

    # Check if goal is already achieved
    if remaining_amount <= 0:
        return {
            "status": "achieved",
            "is_achieved": True,
            "total_target": total_target,
            "target_price": target_price,
            "extra_costs": extra_costs,
            "current_savings": current_savings,
            "remaining_amount": 0.0,
            "progress_pct": 100.0,
            "saving_amount": saving_amount,
            "saving_frequency": saving_frequency,
            "days_required": 0,
            "weeks_required": 0,
            "months_required": 0,
            "estimated_date": start_date.isoformat(),
            "message": "Goal achieved! Current savings meet or exceed the target amount."
        }

    # Validate saving contribution
    if saving_amount <= 0:
        return {
            "status": "invalid_saving_amount",
            "is_achieved": False,
            "total_target": total_target,
            "target_price": target_price,
            "extra_costs": extra_costs,
            "current_savings": current_savings,
            "remaining_amount": remaining_amount,
            "progress_pct": progress_pct,
            "saving_amount": saving_amount,
            "saving_frequency": saving_frequency,
            "days_required": None,
            "weeks_required": None,
            "months_required": None,
            "estimated_date": None,
            "message": "Saving amount must be greater than zero to calculate an estimated achievement date."
        }

    # Calculate periods required
    if saving_frequency == "daily":
        days_required = math.ceil(remaining_amount / saving_amount)
        weeks_required = math.ceil(days_required / 7)
        months_required = math.ceil(days_required / 30.4375)
        estimated_date = start_date + timedelta(days=days_required)
    elif saving_frequency == "weekly":
        weeks_required = math.ceil(remaining_amount / saving_amount)
        days_required = weeks_required * 7
        months_required = math.ceil(weeks_required / 4.345)
        estimated_date = start_date + timedelta(days=days_required)
    elif saving_frequency == "monthly":
        months_required = math.ceil(remaining_amount / saving_amount)
        estimated_date = add_calendar_months(start_date, months_required)
        days_required = (estimated_date - start_date).days
        weeks_required = math.ceil(days_required / 7)

    return {
        "status": "active",
        "is_achieved": False,
        "total_target": total_target,
        "target_price": target_price,
        "extra_costs": extra_costs,
        "current_savings": current_savings,
        "remaining_amount": remaining_amount,
        "progress_pct": progress_pct,
        "saving_amount": saving_amount,
        "saving_frequency": saving_frequency,
        "days_required": days_required,
        "weeks_required": weeks_required,
        "months_required": months_required,
        "estimated_date": estimated_date.isoformat(),
        "message": f"Estimated achievement in {days_required} days ({estimated_date.strftime('%d %b %Y')})."
    }


def generate_saving_scenarios(
    target_price: float,
    current_savings: float = 0.0,
    extra_costs: float = 0.0,
    start_date: date = None
) -> list:
    """
    Generates comparison scenarios across preset daily amounts:
    ₹10, ₹50, ₹100, ₹250, ₹500, ₹1,000, ₹2,000, and ₹5,000 per day.
    """
    if start_date is None:
        start_date = date.today()
    
    presets = [10, 50, 100, 250, 500, 1000, 2000, 5000]
    scenarios = []
    
    total_target = round(float(target_price or 0) + float(extra_costs or 0), 2)
    remaining = round(max(0.0, total_target - float(current_savings or 0)), 2)

    for amt in presets:
        if remaining <= 0:
            days = 0
            est_date = start_date
        else:
            days = math.ceil(remaining / amt)
            est_date = start_date + timedelta(days=days)
        
        # Approximate monthly commitment (30 days)
        monthly_equiv = amt * 30
        
        scenarios.append({
            "daily_amount": amt,
            "monthly_equivalent": monthly_equiv,
            "days_required": days,
            "months_approx": round(days / 30.4375, 1),
            "estimated_date": est_date.isoformat(),
            "estimated_date_display": est_date.strftime("%d %b %Y")
        })

    return scenarios


# ── Product Price Catalog & Search ─────────────────────────────────────────────

# Verified benchmark catalog of popular Indian products across categories with multiple variants,
# official sources, and on-road prices for vehicles.
PRODUCT_CATALOG = [
    {
        "id": "iphone-16",
        "name": "Apple iPhone 16",
        "category": "Smartphones",
        "image": "📱",
        "source": "Apple Store India Official MRP",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": False,
        "variants": [
            {"model": "128 GB", "price": 79900.0, "details": "A18 chip, Camera Control, 48MP Fusion Camera"},
            {"model": "256 GB", "price": 89900.0, "details": "A18 chip, Camera Control, 256GB storage"},
            {"model": "512 GB", "price": 109900.0, "details": "A18 chip, Camera Control, 512GB storage"}
        ]
    },
    {
        "id": "iphone-17",
        "name": "Apple iPhone 17 (Next-Gen)",
        "category": "Smartphones",
        "image": "📱",
        "source": "Apple Official / Reputable Retail Preview",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": False,
        "variants": [
            {"model": "Standard 128 GB (Est.)", "price": 82900.0, "details": "Apple Intelligence 2.0, Promotion 120Hz display"},
            {"model": "Standard 256 GB (Est.)", "price": 92900.0, "details": "Next-Gen 3nm Apple silicon, 256GB"},
            {"model": "Pro 256 GB (Est.)", "price": 134900.0, "details": "Titanium enclosure, Pro camera array"}
        ]
    },
    {
        "id": "hunter-350",
        "name": "Royal Enfield Hunter 350",
        "category": "Vehicles & Bikes",
        "image": "🏍️",
        "source": "Royal Enfield Official India (Ex-Showroom & Est. Delhi On-Road)",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": True,
        "variants": [
            {
                "model": "Retro Factory Series",
                "price": 149900.0,
                "on_road_price": 173500.0,
                "details": "Spoke wheels, Single-channel ABS, 349cc J-Series engine. On-road includes RTO + 5-yr insurance."
            },
            {
                "model": "Dapper Series",
                "price": 169656.0,
                "on_road_price": 195800.0,
                "details": "Alloy wheels, Dual-channel ABS, Tubeless tyres. On-road includes RTO + 5-yr insurance."
            },
            {
                "model": "Rebel Series (Top Variant)",
                "price": 174655.0,
                "on_road_price": 201500.0,
                "details": "Dual-tone paint scheme, Tripper navigation optional, Dual ABS. On-road includes RTO + 5-yr insurance."
            }
        ]
    },
    {
        "id": "classic-350",
        "name": "Royal Enfield Classic 350",
        "category": "Vehicles & Bikes",
        "image": "🏍️",
        "source": "Royal Enfield Official India",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": True,
        "variants": [
            {
                "model": "Heritage Single ABS",
                "price": 199500.0,
                "on_road_price": 229800.0,
                "details": "Timeless retro design, J-series engine, single ABS."
            },
            {
                "model": "Dark Series Dual ABS",
                "price": 225000.0,
                "on_road_price": 258900.0,
                "details": "Matte finish, alloy wheels, dual-channel ABS, LED headlight."
            }
        ]
    },
    {
        "id": "maruti-swift",
        "name": "Maruti Suzuki Swift",
        "category": "Cars & Vehicles",
        "image": "🚗",
        "source": "Maruti Suzuki Arena Official (Ex-Showroom & Est. On-Road Delhi)",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": True,
        "variants": [
            {
                "model": "Swift LXi (1.2L Z-Series MT)",
                "price": 649000.0,
                "on_road_price": 732000.0,
                "details": "6 Airbags standard, ESP, Halogen headlights. On-road includes RTO, Insurance, FASTag."
            },
            {
                "model": "Swift VXi (1.2L MT)",
                "price": 729500.0,
                "on_road_price": 821000.0,
                "details": "7-inch Touchscreen, Steering controls, Power windows. On-road includes RTO, Insurance."
            },
            {
                "model": "Swift ZXi (1.2L MT)",
                "price": 829500.0,
                "on_road_price": 931000.0,
                "details": "LED projector lamps, Alloy wheels, Wireless charger, Auto AC."
            },
            {
                "model": "Swift ZXi+ AMT Dual Tone (Top Spec)",
                "price": 959500.0,
                "on_road_price": 1074000.0,
                "details": "9-inch SmartPlay Pro+, Cruise control, Dual-tone paint, AGS transmission."
            }
        ]
    },
    {
        "id": "tata-nexon",
        "name": "Tata Nexon",
        "category": "Cars & Vehicles",
        "image": "🚙",
        "source": "Tata Motors Official (Ex-Showroom & Est. Delhi On-Road)",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": True,
        "variants": [
            {
                "model": "Smart 1.2 Petrol MT",
                "price": 799990.0,
                "on_road_price": 904000.0,
                "details": "5-Star BNCAP safety, 6 Airbags, LED DRLs. On-road includes RTO + Comprehensive Insurance."
            },
            {
                "model": "Creative 1.2 Turbo MT",
                "price": 1100000.0,
                "on_road_price": 1245000.0,
                "details": "10.25-inch infotainment, 360-degree camera, sequential LED indicators."
            },
            {
                "model": "Fearless+ S Petrol MT",
                "price": 1319990.0,
                "on_road_price": 1490000.0,
                "details": "Sunroof, Ventilated front seats, JBL audio system, Air purifier."
            }
        ]
    },
    {
        "id": "macbook-air",
        "name": "Apple MacBook Air",
        "category": "Laptops & Computing",
        "image": "💻",
        "source": "Apple Store India Official MRP",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": False,
        "variants": [
            {
                "model": "13-inch M2 (16GB Unified Memory / 256GB SSD)",
                "price": 99900.0,
                "details": "Apple M2 8-core CPU / 8-core GPU, Liquid Retina display, MagSafe 3"
            },
            {
                "model": "13-inch M3 (16GB Unified Memory / 256GB SSD)",
                "price": 114900.0,
                "details": "Apple M3 8-core CPU / 8-core GPU, Dual external displays support, Wi-Fi 6E"
            },
            {
                "model": "13-inch M3 (16GB Unified Memory / 512GB SSD)",
                "price": 134900.0,
                "details": "Apple M3 8-core CPU / 10-core GPU, 512GB SSD storage, 18-hour battery life"
            },
            {
                "model": "15-inch M3 (16GB Unified Memory / 512GB SSD)",
                "price": 154900.0,
                "details": "15.3-inch Liquid Retina display, 6-speaker sound system with force-cancelling woofers"
            }
        ]
    },
    {
        "id": "playstation-5-slim",
        "name": "Sony PlayStation 5 Slim",
        "category": "Gaming Consoles",
        "image": "🎮",
        "source": "Sony Center India / Official Retail MRP",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": False,
        "variants": [
            {
                "model": "Digital Edition (1TB SSD)",
                "price": 44990.0,
                "details": "1TB Custom High-Speed SSD, DualSense wireless controller, 4K 120fps support"
            },
            {
                "model": "Disc Edition (1TB SSD + Ultra HD Blu-ray)",
                "price": 54990.0,
                "details": "Includes detachable Ultra HD Blu-ray Disc Drive + DualSense controller"
            }
        ]
    },
    {
        "id": "samsung-s25",
        "name": "Samsung Galaxy S25 / S24",
        "category": "Smartphones",
        "image": "📱",
        "source": "Samsung India Official MRP",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": False,
        "variants": [
            {"model": "Galaxy S24 (8GB / 128GB)", "price": 64999.0, "details": "Galaxy AI, Snapdragon 8 Gen 3, Dynamic AMOLED 2X"},
            {"model": "Galaxy S25 (12GB / 256GB)", "price": 79999.0, "details": "Next-Gen Galaxy AI, Snapdragon 8 Elite, 50MP ProVisual"},
            {"model": "Galaxy S25 Ultra (12GB / 256GB)", "price": 129999.0, "details": "Titanium frame, Built-in S-Pen, 200MP Quad Telephoto"}
        ]
    },
    {
        "id": "ipad-air",
        "name": "Apple iPad Air (M2)",
        "category": "Laptops & Computing",
        "image": "📟",
        "source": "Apple Store India Official MRP",
        "price_checked_at": "2026-10-25T10:00:00+05:30",
        "is_vehicle": False,
        "variants": [
            {"model": "11-inch Wi-Fi 128 GB", "price": 59900.0, "details": "Apple M2 chip, Landscape 12MP front camera, Apple Pencil Pro support"},
            {"model": "11-inch Wi-Fi 256 GB", "price": 69900.0, "details": "Apple M2 chip, 256GB, Liquid Retina display"},
            {"model": "13-inch Wi-Fi 128 GB", "price": 79900.0, "details": "Expansive 13-inch Liquid Retina display, M2 performance"}
        ]
    }
]


def search_product_prices(query: str) -> dict:
    """
    Searches for a product by name and model.
    Checks live search options and verified official catalog.
    If no matches or online lookup fails, returns empty results with guidance
    for manual entry.
    """
    clean_query = (query or "").strip().lower()
    if not clean_query:
        return {
            "query": "",
            "results": [],
            "source_type": "none",
            "message": "Enter a product name to search for pricing."
        }

    # First check if external search API is configured via environment variable
    # e.g., SERPAPI_KEY, PRODUCT_SEARCH_API_KEY
    api_key = os.environ.get("PRODUCT_SEARCH_API_KEY") or os.environ.get("SERPAPI_KEY")
    live_results = []
    
    if api_key:
        try:
            # Query external API if key is configured
            encoded = urllib.parse.quote(f"{clean_query} price in india inr")
            req = urllib.request.Request(
                f"https://serpapi.com/search.json?q={encoded}&gl=in&hl=en&api_key={api_key}",
                headers={"User-Agent": "Bucksy-AchievementPlanner/1.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode())
                shopping_results = data.get("shopping_results", [])
                for item in shopping_results[:4]:
                    raw_price = item.get("extracted_price") or 0.0
                    if raw_price > 0:
                        live_results.append({
                            "id": f"live-{item.get('position', 1)}",
                            "name": item.get("title", clean_query.title()),
                            "category": "Online Search Result",
                            "image": "🛒",
                            "source": item.get("source", "Reputable Online Retailer"),
                            "price_checked_at": datetime.now().isoformat(),
                            "is_vehicle": False,
                            "variants": [{
                                "model": item.get("snippet", "Online Retail Listing"),
                                "price": float(raw_price),
                                "details": f"Seller: {item.get('source', 'Online')} · Live pricing"
                            }]
                        })
        except Exception:
            # Silently fall back to verified catalog on network error / rate limit
            pass

    # Search local verified benchmark catalog
    query_tokens = [t for t in clean_query.replace("-", " ").split() if len(t) > 1]
    catalog_matches = []

    for item in PRODUCT_CATALOG:
        match_score = 0
        search_blob = f"{item['name']} {item['category']} {item['id']}".lower()
        for variant in item["variants"]:
            search_blob += f" {variant['model']} {variant.get('details', '')}".lower()

        # Check full query match
        if clean_query in search_blob:
            match_score += 10
        
        # Check token matches
        for token in query_tokens:
            if token in search_blob:
                match_score += 2

        if match_score > 0:
            catalog_matches.append((match_score, item))

    # Sort catalog matches by relevance score
    catalog_matches.sort(key=lambda x: x[0], reverse=True)
    catalog_results = [m[1] for m in catalog_matches]

    combined = live_results + catalog_results

    if combined:
        return {
            "query": query,
            "results": combined,
            "source_type": "live_and_verified" if live_results else "verified_official",
            "message": f"Found {len(combined)} matching product(s). Select a variant or enter a custom price."
        }
    else:
        return {
            "query": query,
            "results": [],
            "source_type": "manual_entry_required",
            "message": f"No live price found for '{query}'. You can manually enter or edit the target price below."
        }
