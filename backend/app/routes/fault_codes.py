"""Fault-code doctor for UK heating engineers. KB first, LLM fallback."""
from fastapi import APIRouter, Depends, HTTPException, Query
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/fault-codes", tags=["fault-codes"])

LABOUR_RATE = 65.0
VAT_RATE = 0.20

# brand -> code -> entry (codes stored normalised: uppercase, no dots/spaces)
KB: dict[str, dict[str, dict]] = {
    "worcester": {
        "EA": {"title": "No flame detected", "meaning": "Boiler tried to ignite but no flame was established.",
               "likely_causes": ["Gas supply interrupted", "Condensate pipe frozen/blocked", "Faulty ignition electrodes", "Blocked flue"],
               "safe_checks": ["Check other gas appliances work", "Check condensate pipe for ice/blockage", "Reset once only — if EA returns, stop and call engineer"],
               "parts": [{"name": "Ignition electrode set", "typical_price_gbp": 45}, {"name": "Condensate pipe insulation", "typical_price_gbp": 15}],
               "danger_level": "caution", "related_quote_hint": "Check gas supply + condensate first; likely electrode replacement."},
        "D5": {"title": "External fault / low system pressure", "meaning": "System water pressure below operating minimum.",
               "likely_causes": ["Slow leak on system", "Recently bled radiators", "Faulty pressure sensor", "Expansion vessel lost charge"],
               "safe_checks": ["Read pressure gauge (should be 1–1.5 bar cold)", "Top up via filling loop to 1.2 bar", "Check visible pipework for leaks"],
               "parts": [{"name": "Expansion vessel", "typical_price_gbp": 120}, {"name": "Pressure sensor", "typical_price_gbp": 55}],
               "danger_level": "safe", "related_quote_hint": "Re-pressurise + leak check; suspect expansion vessel if recurring."},
        "E9": {"title": "Overheat lockout", "meaning": "Heat exchanger temperature exceeded safe limit.",
               "likely_causes": ["Pump seized or airlocked", "Blocked heat exchanger (sludge)", "No circulation — valves closed"],
               "safe_checks": ["Let boiler cool 30 minutes", "Check pump is running/vibrating", "Bleed radiators", "Do NOT repeatedly reset"],
               "parts": [{"name": "Central heating pump", "typical_price_gbp": 180}, {"name": "Powerflush (system clean)", "typical_price_gbp": 350}],
               "danger_level": "caution", "related_quote_hint": "Pump check first; powerflush if sludge suspected."},
        "C6": {"title": "Fan fault", "meaning": "Fan not running at expected speed.",
               "likely_causes": ["Seized fan", "Blocked flue/air intake", "Faulty fan PCB connection"],
               "safe_checks": ["Visually check flue terminal is clear outside", "Listen for fan attempting to start"],
               "parts": [{"name": "Fan assembly", "typical_price_gbp": 160}],
               "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe only — fan/flue compartment."},
        "E2": {"title": "Flue / fan safety fault", "meaning": "Flue gas safety interlock triggered.",
               "likely_causes": ["Blocked flue", "Failed flue sensor", "Condensate backup into flue"],
               "safe_checks": ["Check flue terminal clear", "Check condensate route clear", "Do not use boiler until inspected"],
               "parts": [{"name": "Flue gas sensor", "typical_price_gbp": 70}],
               "danger_level": "gas_safe_only", "related_quote_hint": "Do not use; Gas Safe inspection required."},
    },
    "vaillant": {
        "F22": {"title": "Low water pressure", "meaning": "System pressure below 0.6 bar.",
                "likely_causes": ["Water loss/leak", "Bled radiators recently", "Faulty pressure sensor"],
                "safe_checks": ["Top up to 1.0–1.5 bar via filling loop", "Inspect for visible leaks", "Monitor for 24h"],
                "parts": [{"name": "Pressure sensor", "typical_price_gbp": 60}],
                "danger_level": "safe", "related_quote_hint": "Top-up + leak inspection."},
        "F28": {"title": "Ignition failure", "meaning": "No flame after ignition attempts — gas/air fault.",
                "likely_causes": ["No gas (prepayment meter?)", "Faulty gas valve", "Ignition electrode failure", "Blocked condensate"],
                "safe_checks": ["Confirm gas supply (hob/other appliances)", "Check condensate pipe", "Reset once only"],
                "parts": [{"name": "Gas valve", "typical_price_gbp": 190}, {"name": "Ignition electrodes", "typical_price_gbp": 50}],
                "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe only — likely gas valve."},
        "F29": {"title": "Flame loss during operation", "meaning": "Flame established then lost — supply/intermittent fault.",
                "likely_causes": ["Intermittent gas supply", "Recirculation (flue too close to intake)", "Condensate issue", "Gas valve fault"],
                "safe_checks": ["Check gas supply stability", "Note weather/wind at time of fault", "Check condensate"],
                "parts": [{"name": "Gas valve", "typical_price_gbp": 190}],
                "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe diagnosis; check flue siting."},
        "F54": {"title": "Gas pressure fault", "meaning": "Inlet gas pressure out of range.",
                "likely_causes": ["Undersized/restricted gas supply", "Faulty gas valve", "Meter governor fault (supplier)"],
                "safe_checks": ["Do not adjust gas pipework", "Check with gas supplier if area issue"],
                "parts": [{"name": "Gas valve", "typical_price_gbp": 190}],
                "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe + possible supplier involvement."},
        "F61": {"title": "Gas valve control fault", "meaning": "PCB cannot control the gas valve correctly.",
                "likely_causes": ["Faulty gas valve", "PCB fault", "Wiring harness fault"],
                "safe_checks": ["Power off/on once at fused spur", "If returns, stop — engineer required"],
                "parts": [{"name": "Gas valve", "typical_price_gbp": 190}, {"name": "Main PCB", "typical_price_gbp": 240}],
                "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe only; valve or PCB."},
    },
    "ideal": {
        "L2": {"title": "Ignition lockout", "meaning": "Burner failed to ignite.",
               "likely_causes": ["No gas supply", "Condensate blockage", "Ignition lead/electrode", "Flue blockage"],
               "safe_checks": ["Check gas supply", "Check condensate pipe (frozen?)", "Reset once only"],
               "parts": [{"name": "Ignition assembly", "typical_price_gbp": 55}],
               "danger_level": "caution", "related_quote_hint": "Condensate check first in winter."},
        "F1": {"title": "Low pressure", "meaning": "System pressure too low.",
               "likely_causes": ["Leak", "Recent bleeding", "Sensor fault"],
               "safe_checks": ["Top up to 1–1.5 bar", "Look for leaks"],
               "parts": [{"name": "Pressure sensor", "typical_price_gbp": 50}],
               "danger_level": "safe", "related_quote_hint": "Top-up + leak check."},
        "F2": {"title": "Flame loss", "meaning": "Flame lost during operation.",
               "likely_causes": ["Gas supply interruption", "Flue recirculation", "Electrode fault"],
               "safe_checks": ["Confirm gas supply", "Reset once", "Note conditions"],
               "parts": [{"name": "Detection electrode", "typical_price_gbp": 40}],
               "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe diagnosis."},
        "L9": {"title": "Blocked flue / condensate", "meaning": "Flue or condensate path blocked.",
               "likely_causes": ["Frozen condensate (winter)", "Blocked flue terminal", "Siphon blockage"],
               "safe_checks": ["Thaw/lag condensate pipe", "Clear flue terminal", "Check siphon"],
               "parts": [{"name": "Condensate insulation kit", "typical_price_gbp": 15}],
               "danger_level": "caution", "related_quote_hint": "Classic winter callout; insulate after."},
        "C6": {"title": "Fan fault", "meaning": "Fan proving failed.",
               "likely_causes": ["Seized fan", "Blocked venturi", "Wiring fault"],
               "safe_checks": ["Check flue clear", "Listen for fan"],
               "parts": [{"name": "Fan unit", "typical_price_gbp": 150}],
               "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe only."},
    },
    "baxi": {
        "E133": {"title": "Ignition lockout", "meaning": "No flame detected after attempts.",
                 "likely_causes": ["Gas supply off", "Condensate frozen", "Electrode/lead failure"],
                 "safe_checks": ["Check gas supply", "Check condensate", "Reset once (hold 2s)"],
                 "parts": [{"name": "Ignition electrode", "typical_price_gbp": 45}],
                 "danger_level": "caution", "related_quote_hint": "Hold-reset, then condensate check."},
        "E168": {"title": "Internal fault lockout", "meaning": "PCB internal self-check failed.",
                 "likely_causes": ["PCB fault", "Power surge damage", "Wiring short"],
                 "safe_checks": ["Power off 2 minutes at spur, retry once"],
                 "parts": [{"name": "Main PCB", "typical_price_gbp": 220}],
                 "danger_level": "gas_safe_only", "related_quote_hint": "Likely PCB; Gas Safe only."},
        "E128": {"title": "Flame loss", "meaning": "Flame lost in operation.",
                 "likely_causes": ["Gas interruption", "Flue issue", "Sensing fault"],
                 "safe_checks": ["Check gas supply", "Reset once"],
                 "parts": [{"name": "Flame sensing electrode", "typical_price_gbp": 40}],
                 "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe diagnosis."},
        "E125": {"title": "Circulation fault", "meaning": "Overheat due to poor circulation.",
                 "likely_causes": ["Pump failure", "Airlock", "Sludge blockage", "Closed valves"],
                 "safe_checks": ["Cool down, check pump running", "Bleed rads", "Check valves open"],
                 "parts": [{"name": "Pump", "typical_price_gbp": 170}],
                 "danger_level": "caution", "related_quote_hint": "Pump/airlock check; flush if sludged."},
    },
    "viessmann": {
        "F2": {"title": "Overheat shutdown", "meaning": "Flow temperature exceeded limit.",
               "likely_causes": ["Pump fault", "Airlock", "Blocked plate heat exchanger", "Sensor drift"],
               "safe_checks": ["Cool down, verify pump", "Bleed system"],
               "parts": [{"name": "Pump", "typical_price_gbp": 175}],
               "danger_level": "caution", "related_quote_hint": "Circulation fault; check pump."},
        "F4": {"title": "No flame signal", "meaning": "Ignition without flame detection.",
               "likely_causes": ["Gas supply", "Ionisation electrode", "Condensate", "Gas valve"],
               "safe_checks": ["Check gas supply + condensate", "Reset once"],
               "parts": [{"name": "Ionisation electrode", "typical_price_gbp": 55}],
               "danger_level": "gas_safe_only", "related_quote_hint": "Gas Safe diagnosis."},
        "EE": {"title": "Communication fault", "meaning": "Controls/PCB communication lost.",
               "likely_causes": ["Loose KM-BUS connection", "Control unit fault", "PCB fault"],
               "safe_checks": ["Power cycle once", "Check external controls wired firmly"],
               "parts": [{"name": "Control unit", "typical_price_gbp": 200}],
               "danger_level": "caution", "related_quote_hint": "Controls check first."},
    },
}


def _norm(code: str) -> str:
    return (code or "").upper().replace(".", "").replace(" ", "").replace("-", "")


def _find(brand: str, code: str):
    b = (brand or "").strip().lower()
    c = _norm(code)
    if not c:
        return None, []
    brands = [b] if b in KB else list(KB.keys())
    for bb in brands:
        if c in KB[bb]:
            e = dict(KB[bb][c])
            e.update({"brand": bb.title(), "code": c})
            return e, []
    sugg = []
    for bb in brands:
        for k, e in KB[bb].items():
            if c in k or k in c:
                sugg.append({"brand": bb.title(), "code": k, "title": e["title"]})
    return None, sugg[:8]


@router.get("/brands")
async def list_brands(current_user=Depends(get_current_user)):
    return {"brands": [{"id": b, "name": b.title(), "codes": len(KB[b])} for b in KB]}


@router.get("/lookup")
async def lookup(code: str = Query(""), brand: str = Query(""),
                 current_user=Depends(get_current_user)):
    if not _norm(code):
        raise HTTPException(status_code=400, detail="code is required")
    entry, sugg = _find(brand, code)
    if entry:
        return {"match_type": "exact", "entry": entry, "source": "kb"}
    return {"match_type": "suggestions", "entry": None, "suggestions": sugg, "source": "kb"}


@router.post("/ask")
async def ask_fault(data: dict, current_user=Depends(get_current_user)):
    brand = str(data.get("brand", "") or "")
    code = str(data.get("code", "") or "")
    entry, sugg = _find(brand, code)
    if entry:
        return {"match_type": "exact", "entry": entry, "source": "kb"}
    if sugg:
        return {"match_type": "suggestions", "entry": None, "suggestions": sugg, "source": "kb"}
    # LLM fallback for unknown codes
    try:
        from app.services import llm
        if llm.is_configured():
            raw = await llm.complete_json(
                f"A heating engineer reports fault code '{code}' on a '{brand or 'unknown'}' boiler. "
                + (f"Symptom: {data.get('symptom_text')}. " if data.get("symptom_text") else "")
                + 'Return ONLY valid JSON: {"title": str, "meaning": str, "likely_causes": [str], '
                + '"safe_checks": [str], "parts": [{"name": str, "typical_price_gbp": number}], '
                + '"danger_level": "safe"|"caution"|"gas_safe_only", "related_quote_hint": str}. UK Gas Safe aware.',
                system="You are a UK heating engineer advisor. Return ONLY valid JSON.",
                max_tokens=600, temperature=0.2)
            raw["brand"] = (brand or "Unknown").title()
            raw["code"] = _norm(code)
            return {"match_type": "exact", "entry": raw, "source": "ai"}
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Unknown code — check spelling")


@router.post("/to-quote")
async def fault_to_quote(data: dict, current_user=Depends(get_current_user)):
    entry, _ = _find(str(data.get("brand", "") or ""), str(data.get("code", "") or ""))
    if not entry:
        raise HTTPException(status_code=404, detail="Unknown code")
    lines = [{"description": p["name"], "quantity": 1, "unit_price": float(p["typical_price_gbp"])}
             for p in entry.get("parts", [])]
    lines.append({"description": f"Labour — {entry['title']} diagnosis & repair", "quantity": 1,
                  "unit_price": LABOUR_RATE})
    subtotal = round(sum(l["quantity"] * l["unit_price"] for l in lines), 2)
    vat = round(subtotal * VAT_RATE, 2)
    return {"title": f"{entry['brand']} {entry['code']} — {entry['title']}",
            "lines": lines, "subtotal": subtotal, "vat": vat,
            "total": round(subtotal + vat, 2)}
