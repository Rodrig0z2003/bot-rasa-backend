import requests
import re
import math
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, ConversationPaused, UserUtteranceReverted, Restarted

# --- ¡CONFIGURA ESTAS URLS! ---
#LARAVEL_WEBHOOK_URL = "http://localhost:8001/api/rasa-order"
#LARAVEL_WEBHOOK_URL = "https://dev.gangsheet-builders.com/api/rasa-order"
#LARAVEL_UPLOAD_PAGE_URL = "http://localhost:8001/upload-order-file"
#LARAVEL_UPLOAD_PAGE_URL = "https://dev.gangsheet-builders.com/upload-order-file"

# ---------------------------------DTT ORDERS.......
LARAVEL_WEBHOOK_URL = "https://dttorders.gangsheet-builders.com/api/rasa-order"
#LARAVEL_UPLOAD_PAGE_URL = "http://localhost:8001/upload-order-file"
LARAVEL_UPLOAD_PAGE_URL = "https://dttorders.gangsheet-builders.com/upload-order-file"

# ---------------------------------

# --- MAPA DE ESTADOS DE EE.UU. ---
US_STATES_MAP = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "puerto rico": "PR"
}

# --- PRECIOS LINEALES (Base por 12 pulgadas) ---
DTF_PRICE_PER_FOOT = 5.00  # Base 22" ancho
UV_PRICE_PER_FOOT = 6.00   # Base 11" ancho

# --- PRECIOS ESPECIALES (Excepciones para rollos grandes de DTF) ---
DTF_BUNDLE_PRICES = {
    238: 95.00,   
    274: 100.00,  
    286: 105.00,  
    300: 105.00   
}

# -------------------------------------------------------------------------
# CLASE 1: CALCULAR PRECIO (Con lógica de Bundles)
# -------------------------------------------------------------------------
class ActionGetPrice(Action):
    def name(self) -> Text:
        return "action_get_price"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        sheet_size = tracker.get_slot("sheet_size")
        product_name = tracker.get_slot("product_name")
        user_message = tracker.latest_message.get('text', '').lower()
        
        response_text = ""
        price = 0.0

        # 1. Detectar si es UV
        is_uv = False
        if (product_name and "uv" in product_name.lower()) or "uv" in user_message:
            is_uv = True

        # 2. Buscar medidas en el mensaje
        feet_match = re.search(r'(\d+(\.\d+)?)\s*(feet|ft|pies)', user_message)
        inch_match = re.search(r'(\d+(\.\d+)?)\s*(inches|inch|in)', user_message)
        size_match = re.search(r'(\d+)[xX](\d+)', user_message)

        length_in_inches = 0.0 
        found_calculation = False
        description = ""

        # --- EXTRACCIÓN DE MEDIDAS ---
        if feet_match:
            feet = float(feet_match.group(1))
            length_in_inches = feet * 12
            description = f"{feet} feet ({length_in_inches:.0f} inches)"
            found_calculation = True
        elif inch_match:
            length_in_inches = float(inch_match.group(1))
            description = f"{length_in_inches:.0f} inches"
            found_calculation = True
        elif size_match:
            val1 = float(size_match.group(1))
            val2 = float(size_match.group(2))
            length = val2
            if val1 > 24 and val1 > val2: length = val1
            
            length_in_inches = length
            description = f"{length:.0f} inches"
            found_calculation = True
        elif sheet_size and "x" in sheet_size:
            try:
                parts = sheet_size.lower().split('x')
                length_in_inches = float(parts[1])
                description = sheet_size
                found_calculation = True
            except: pass

        # --- CÁLCULO DE PRECIO ---
        if found_calculation:
            length_int = int(length_in_inches)

            if is_uv:
                price = (length_in_inches / 12) * UV_PRICE_PER_FOOT
                response_text = f"A **UV DTF Gang Sheet** (11\" wide) of **{description}** costs **${price:.2f}**."
            else:
                if length_int in DTF_BUNDLE_PRICES:
                    price = DTF_BUNDLE_PRICES[length_int]
                    response_text = f"A **DTF Gang Sheet** (22\" wide) of **{description}** has a special bundle price of **${price:.2f}**."
                else:
                    price = (length_in_inches / 12) * DTF_PRICE_PER_FOOT
                    response_text = f"A **DTF Gang Sheet** (22\" wide) of **{description}** costs **${price:.2f}**."
        else:
            if is_uv:
                response_text = "Our UV DTF Gang Sheets start at **$6.00 per linear foot**."
            else:
                response_text = "Our DTF Gang Sheets start at **$5.00 per linear foot**. Large rolls (like 22x300) have special discounted pricing!"

        dispatcher.utter_message(text=response_text)
        return []


# -------------------------------------------------------------------------
# CLASE: PREGUNTAR CATEGORÍA (BOTONES GRID)
# -------------------------------------------------------------------------
class ActionAskCategory(Action):
    def name(self) -> Text:
        return "action_ask_category"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        product = tracker.get_slot("product_name")
        
        msg = "Are you purchasing a pre-set gang sheet size, or do you need a custom size?"
        
        if product and "uv" in product.lower():
            opt1_title = "UV DTF Gang Sheet "
            opt1_payload = '/inform{"category":"UV DTF Gang Sheet"}'
        else:
            opt1_title = "DTF Gang Sheet "
            opt1_payload = '/inform{"category":"DTF Gang Sheet"}'

        custom_grid = {
            "type": "grid",
            "text": msg,
            "options": [
                {
                    "title": opt1_title,
                    "payload": opt1_payload
                },
                {
                    "title": "Print by size ",
                    "payload": '/inform{"category":"Print by size"}'
                }
            ]
        }
        
        dispatcher.utter_message(json_message=custom_grid)
        return []


# -------------------------------------------------------------------------
# CLASE: PREGUNTAR CANTIDAD (DINÁMICO)
# -------------------------------------------------------------------------
class ActionAskQuantity(Action):
    def name(self) -> Text:
        return "action_ask_quantity"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Obtenemos AMBOS slots
        product = tracker.get_slot("product_name")
        subtype = tracker.get_slot("tshirt_subtype") 

        # Normalizamos (quitamos espacios y ponemos minúsculas para comparar)
        check_val = ""
        if subtype:
            check_val = subtype.lower().strip()
        elif product:
            check_val = product.lower().strip()

        # LÓGICA DE MENSAJES
        # CASO 1: Custom T-shirts ($10.99) -> CON ADVERTENCIA
        if "custom t-shirts" in check_val or "customs t-shirt" in check_val:
            dispatcher.utter_message(text="⚠️ **Note:** Sizes 2XL, 3XL, and larger have an additional cost.")
            dispatcher.utter_message(text="How many shirts would you like to order?")
            
        # CASO 2: Heat Press ($5.99) -> SIN ADVERTENCIA
        elif "heat press" in check_val:
            dispatcher.utter_message(text="How many shirts do you need us to press?")
            
        # CASO 3: Gang Sheets
        else:
            dispatcher.utter_message(text="How many copies would you like?")

        return []


# -------------------------------------------------------------------------
# CLASE 2: VALIDAR FORMULARIO DE PEDIDO (ACTUALIZADO Y SIMPLIFICADO)
# -------------------------------------------------------------------------
class ValidateOrderForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_order_form"

    async def required_slots(
        self,
        domain_slots: List[Text],
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Optional[List[Text]]:
        
        required = ["product_name"]
        
        product = tracker.get_slot("product_name")
        subtype = tracker.get_slot("tshirt_subtype")
        category = tracker.get_slot("category")
        carrier = tracker.get_slot("carrier")

        # --- CASO 1: SERVICIOS DE ROPA ---
        if product in ["Customs T-Shirt", "Custom T-shirts", "DTF + Heat Press Service"]:
            if product == "Customs T-Shirt":
                if not subtype:
                    required.append("tshirt_subtype")
            required.extend(["quantity", "user_name", "user_email", "carrier"])
            if carrier and ("UPS" in carrier or "Shipping" in carrier):
                required.append("state")
            return required

        # --- CASO 2: GANG SHEETS ---
        required.append("category")

        if category == "Print by size":
            required.extend(["custom_inches", "quantity", "user_name", "user_email", "carrier"])
        else:
            # Aquí pedimos sheet_size
            required.extend(["sheet_size", "quantity", "user_name", "user_email", "carrier"])

        if carrier and ("UPS" in carrier or "Shipping" in carrier):
            required.append("state")

        return required

    # --- VALIDACIONES ---

    def validate_product_name(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"product_name": str(slot_value)}

    def validate_tshirt_subtype(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        subtype = str(slot_value)
        return {"tshirt_subtype": subtype, "product_name": subtype}

    def validate_quantity(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        try:
            qty = float(slot_value)
            return {"quantity": qty} if qty >= 1 else {"quantity": None}
        except:
            dispatcher.utter_message(text="Please enter a valid number.")
            return {"quantity": None}

    def validate_category(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        cat = str(slot_value).lower()
        product = tracker.get_slot("product_name")
        if "print" in cat: return {"category": "Print by size"}
        if product and "uv" in product.lower(): return {"category": "UV DTF Gang Sheet"}
        return {"category": "DTF Gang Sheet"}

    # --- NUEVA LÓGICA ROBUSTA PARA SHEET_SIZE ---
    def validate_sheet_size(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        # 1. Limpieza agresiva para obtener solo el texto (quitamos json artifacts si los hay)
        raw_val = str(slot_value)
        # Regex busca patrón NUMxNUM (ej: 22x24)
        match = re.search(r'(\d+\s*x\s*\d+)', raw_val, re.IGNORECASE)
        
        if match:
            # Encontramos un tamaño válido (ej: "22x24")
            clean_size = match.group(1).replace(" ", "").lower()
            print(f"✅ DEBUG VALIDATION: Tamaño válido encontrado -> {clean_size}")
            return {"sheet_size": clean_size}
        
        # Si no encontramos patrón, intentamos buscar en el historial por si Rasa se confundió con el texto del botón
        print(f"⚠️ DEBUG VALIDATION: Valor '{raw_val}' no parece un tamaño estándar. Buscando en historial...")
        for event in reversed(tracker.events):
            if event.get("event") == "slot" and event.get("name") == "sheet_size":
                prev = str(event.get("value", ""))
                if "x" in prev:
                    return {"sheet_size": prev}

        dispatcher.utter_message(text="Please select a valid size (e.g., 22x12).")
        return {"sheet_size": None}

    def validate_user_name(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        name = str(slot_value).strip()
        if name.lower() in ["stop", "cancel"]: return {"user_name": None}
        return {"user_name": name.title()}

    def validate_user_email(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"user_email": str(slot_value)}
    
    def validate_carrier(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        val = str(slot_value)
        if "Pickup" in val or "San Dimas" in val or "Covina" in val:
            return {"carrier": val, "state": "CA"}
        return {"carrier": val, "state": None}

    def validate_state(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        text = str(slot_value).upper().replace(".", "")
        if len(text) == 2: return {"state": text}
        if text.lower() in US_STATES_MAP: return {"state": US_STATES_MAP[text.lower()]}
        return {"state": text}

    def validate_custom_inches(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        try:
            val_str = str(slot_value).lower().replace("inches", "").replace("inch", "").replace("in", "").strip()
            inches = float(val_str)
        except (ValueError, TypeError):
            dispatcher.utter_message(text="🛑 That is not a valid number. Please enter the total length in inches.")
            return {"custom_inches": None}

        if inches < 1:
            dispatcher.utter_message(text="🛑 The size cannot be 0 or negative.")
            return {"custom_inches": None}

        # Calcular y mostrar precio estimado (Lógica original mantenida para UX)
        inches_int = int(inches)
        dtf_price = globals().get('DTF_PRICE_PER_FOOT', 5.00)
        uv_price = globals().get('UV_PRICE_PER_FOOT', 6.00)
        
        if inches_int in DTF_BUNDLE_PRICES:
             price = DTF_BUNDLE_PRICES[inches_int]
             dispatcher.utter_message(text=f"✅ Got it. {inches_int} inches. Special Bundle Price: **${price:.2f}**!")
        else:
            prod = tracker.get_slot("product_name")
            rate = uv_price if (prod and "uv" in prod.lower()) else dtf_price
            feet = inches / 12
            price = feet * rate
            dispatcher.utter_message(text=f"✅ Got it. {inches} inches is approx {feet:.1f} feet. Estimated price: **${price:.2f}**.")
        
        return {"custom_inches": inches}


# -------------------------------------------------------------------------
# CLASE: ENVIAR PEDIDO A API (ACTUALIZADA Y SIMPLIFICADA)
# -------------------------------------------------------------------------
class ActionSubmitOrderToApi(Action):
    def name(self) -> Text:
        return "action_submit_order_to_api"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Función auxiliar simple
        def clean_str(val):
            if not val: return ""
            return str(val).replace('"', '').replace("'", "").replace("[", "").replace("]", "").strip()

        # 1. RECUPERAR DATOS DEL TRACKER
        category = tracker.get_slot("category")
        custom_inches = tracker.get_slot("custom_inches")
        quantity = tracker.get_slot("quantity")
        state = tracker.get_slot("state")
        raw_product = tracker.get_slot("product_name")
        subtype = tracker.get_slot("tshirt_subtype")
        carrier = clean_str(tracker.get_slot("carrier"))
        
        # 2. RECUPERAR TAMAÑO ACTUAL
        current_slot_size = clean_str(tracker.get_slot("sheet_size"))

        # --- 🛡️ LÓGICA DE RECUPERACIÓN (ANTI-SOBREESCRITURA) ---
        # Si el tamaño actual es inválido (ej: es "1" o vacío), buscamos en el historial
        final_sheet_size = current_slot_size

        if not (final_sheet_size and "x" in final_sheet_size.lower()):
            print(f"⚠️ DEBUG: El tamaño actual '{final_sheet_size}' parece incorrecto (falta 'x'). Buscando en historial...")
            for event in reversed(tracker.events):
                if event.get("event") == "slot" and event.get("name") == "sheet_size":
                    prev_val = clean_str(event.get("value"))
                    # Si encontramos un valor antiguo que SÍ tenga 'x' (ej: 22x12), lo rescatamos
                    if prev_val and "x" in prev_val.lower():
                        final_sheet_size = prev_val
                        print(f"✅ DEBUG: ¡Tamaño recuperado del historial! -> {final_sheet_size}")
                        break
        # -------------------------------------------------------

        # 3. DETERMINAR EL STRING FINAL PARA LARAVEL
        size_to_send = "N/A (Apparel/Service)" 

        # Caso A: Print by Size
        if category == "Print by size" and custom_inches:
            size_to_send = f"{custom_inches} Inches (Custom)"
        
        # Caso B: Gang Sheets (Usamos el valor recuperado)
        elif final_sheet_size and "x" in final_sheet_size.lower():
            size_to_send = final_sheet_size
        
        # 4. DEBUG FINAL
        print(f"\n🚀 ENVIO A LARAVEL:")
        print(f"   - Category: {category}")
        print(f"   - Qty: {quantity}")
        print(f"   - Size Final: {size_to_send}")

        # 5. PREPARAR NOMBRE DEL PRODUCTO
        final_product = clean_str(subtype if subtype else raw_product)

        # 6. CONSTRUIR JSON
        order_data = {
            "product": final_product, 
            "category": category if category else "Apparel",
            "quantity": quantity,
            "size": size_to_send, # <--- Valor corregido
            "customer_name": tracker.get_slot("user_name"),
            "customer_email": tracker.get_slot("user_email"),
            "shipping_method": carrier,
            "state": state,
            "sender_id": tracker.sender_id
        }

        dispatcher.utter_message(text="Perfect! Submitting your order details...")

        # 7. ENVIAR A LARAVEL
        try:
            response = requests.post(LARAVEL_WEBHOOK_URL, json=order_data)
            response.raise_for_status()
            data_resp = response.json()
            order_id = data_resp.get("order_id")
            
            if order_id:
                link = f"{LARAVEL_UPLOAD_PAGE_URL}/{order_id}"
                # Mostrar total calculado por Laravel
                total_msg = f" Total: ${data_resp.get('total', '??')}" if 'total' in data_resp else ""
                dispatcher.utter_message(text=f"Success! Order #{order_id} created.{total_msg}")
                dispatcher.utter_message(text=f"**IMPORTANT:** Please upload your design file here:\n[Click to upload]({link})")
            else:
                dispatcher.utter_message(text="Order created. Check your email.")
        
        except Exception as e:
            print(f"❌ ERROR LARAVEL: {e}")
            dispatcher.utter_message(text="Error submitting order. Please try again.")

        return [SlotSet(s, None) for s in ["product_name", "quantity", "sheet_size", "category", "user_name", "user_email", "carrier", "custom_inches", "tshirt_subtype", "state"]]

class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="OK, I've cancelled this order. What can I help you with next?")
        return [SlotSet(slot, None) for slot in ["product_name", "quantity", "sheet_size", "category", "user_name", "user_email", "carrier", "custom_inches", "tshirt_subtype", "state"]]


class ActionAskSheetSize(Action):
    def name(self) -> Text:
        return "action_ask_sheet_size"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        product_name = tracker.get_slot("product_name")
        category = tracker.get_slot("category")

        utter_action = "utter_ask_sheet_size_dtf"

        if product_name and "uv" in product_name.lower():
            utter_action = "utter_ask_sheet_size_uv"
        elif category and "uv" in category.lower():
            utter_action = "utter_ask_sheet_size_uv"

        dispatcher.utter_message(response=utter_action)
        return []


class ActionHumanHandoff(Action):
    def name(self) -> Text:
        return "action_human_handoff"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(response="utter_handoff_confirmation")
        custom_json = { "type": "handoff_start" }
        dispatcher.utter_message(json_message=custom_json)

        try:
            #webhook_url = "http://localhost:8001/api/live-chat-request"
            #webhook_url = "https://dev.gangsheet-builders.com/api/live-chat-request"
            webhook_url = "https://dttorders.gangsheet-builders.com/api/live-chat-request"
            requests.post(
                webhook_url,
                json={
                    "sender_id": tracker.sender_id,
                    "message": "User requested a human agent!"
                }
            )
        except Exception as e:
            print(f"Error notifying handoff webhook: {e}")

        return [ConversationPaused()]


class ValidateHandoffForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_handoff_form"

    def validate_handoff_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        name = str(slot_value).strip()
        if len(name) < 2:
            dispatcher.utter_message(text="That name seems a bit short. Please enter your full name.")
            return {"handoff_name": None}
        return {"handoff_name": name.title()}


class ActionSubmitHandoff(Action):
    def name(self) -> Text:
        return "action_submit_handoff"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> List[Dict[Text, Any]]:

        customer_name = tracker.get_slot("handoff_name")
        sender_id = tracker.sender_id

        try:
            #webhook_url = "http://localhost:8001/api/live-chat-request"
            #webhook_url = "https://dev.gangsheet-builders.com/api/live-chat-request"
            webhook_url = "https://dttorders.gangsheet-builders.com/api/live-chat-request"
            requests.post(
                webhook_url,
                json={
                    "sender_id": sender_id,
                    "user_name": customer_name,
                    "message": f"User '{customer_name}' requested a human agent!"
                }
            )
        except Exception as e:
            print(f"Error notifying handoff webhook: {e}")
            
        dispatcher.utter_message(response="utter_handoff_confirmation")
        dispatcher.utter_message(json_message={"type": "handoff_start"})

        return [ConversationPaused(), SlotSet("handoff_name", None)]


class ValidateStatusForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_status_form"

    def validate_order_reference(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        
        # Limpiamos el texto
        clean_ref = str(slot_value).strip().upper()
        
        # --- LÓGICA DE VALIDACIÓN ROBUSTA ---
        # 1. Prefijos conocidos
        valid_prefixes = ["RASA-", "DTF-", "UV-", "HP-", "BOT-"]
        has_valid_prefix = any(clean_ref.startswith(prefix) for prefix in valid_prefixes)
        
        # 2. Códigos PrestaShop (letras/números aleatorios)
        # Aceptamos entre 8 y 12 caracteres. Eliminamos espacios internos por si acaso.
        check_prestashop = clean_ref.replace(" ", "")
        is_prestashop = (len(check_prestashop) >= 8 and len(check_prestashop) <= 12)

        if has_valid_prefix or is_prestashop:
            # ¡Es válido! Lo guardamos limpio
            return {"order_reference": clean_ref}
        else:
            # No parece un código válido
            dispatcher.utter_message(text="⚠️ That doesn't look like a valid order code. It should start with RASA-, DTF-, UV-, or be a 9-letter code.")
            return {"order_reference": None}

# -------------------------------------------------------------------------
# CLASE API: CONSULTAR LARAVEL (Simplificada)
# -------------------------------------------------------------------------
class ActionCheckOrderStatus(Action):
    def name(self) -> Text:
        return "action_check_order_status"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Ya sabemos que el slot existe porque el formulario lo pidió
        reference = tracker.get_slot("order_reference")
        
        # URL de tu API Laravel
        #API_URL = "http://localhost:8001/api/rasa-check-status"
        #API_URL = "https://dev.gangsheet-builders.com/api/rasa-check-status"
        API_URL = "https://dttorders.gangsheet-builders.com/api/rasa-check-status"

        dispatcher.utter_message(text=f"Checking status for order {reference}...")

        try:
            response = requests.post(API_URL, json={"reference": reference})
            # print(f"DEBUG: {response.text}") # Descomentar si falla
            
            response.raise_for_status()
            data = response.json()

            if response.status_code == 200 and data.get("found"):
                status = data.get("status")
                carrier = data.get("carrier")
                track_num = data.get("tracking_number")
                hold = data.get("hold_reason")
                customer = data.get("customer")

                msg = f"📦 **Order Status:** {status}\n"
                msg += f"👤 **Customer:** {customer}\n"
                msg += f"🚚 **Carrier:** {carrier}\n"
                
                if track_num and track_num != "Not assigned yet":
                    msg += f"🔢 **Tracking #:** {track_num}\n"
                
                if hold:
                    msg += f"⚠️ **HOLD ALERT:** Your order is on hold: {hold}. Please contact us."
                
                dispatcher.utter_message(text=msg)
            else:
                dispatcher.utter_message(text=f"❌ I searched for **{reference}**, but our system says 'Order not found'. Please double-check the code.")
                
        except Exception as e:
            print(f"Error checking order: {e}")
            dispatcher.utter_message(text="Sorry, I'm having trouble connecting to the tracking system right now.")

        # Reseteamos el slot al final para permitir una nueva búsqueda limpia después
        return [SlotSet("order_reference", None)]

# -------------------------------------------------------------------------
# CLASES DE FALLBACK PROGRESIVO (Nivel 1, 2, 3)
# -------------------------------------------------------------------------

class ActionSmartFallback(Action):
    def name(self) -> Text:
        return "action_smart_fallback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # 1. Obtener contador actual
        current_count = tracker.get_slot("fallback_count")
        if current_count is None:
            current_count = 0.0
        
        # Convertir a float por seguridad
        try:
            current_val = float(current_count)
        except:
            current_val = 0.0

        print(f"DEBUG: Fallback triggered. Current count: {current_val}")

        # 2. Lógica de 3 niveles
        if current_val == 0.0:
            # Intento 1
            dispatcher.utter_message(response="utter_default")
            # SOLO actualizamos el slot, NO revertimos
            return [SlotSet("fallback_count", 1.0)]
        
        elif current_val == 1.0:
            # Intento 2
            dispatcher.utter_message(response="utter_default_help")
            # Actualizamos a 2
            return [SlotSet("fallback_count", 2.0)]
        
        else:
            # Intento 3 (>= 2.0) -> Reinicio
            dispatcher.utter_message(response="utter_restart")
            # Aquí SÍ reiniciamos todo el bot
            return [Restarted(), SlotSet("fallback_count", 0.0)]

class ActionCalculateQuote(Action):
    def name(self) -> Text:
        return "action_calculate_quote"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # 1. Obtener datos de los slots
        raw_product = tracker.get_slot("quote_product")
        size = tracker.get_slot("quote_size")
        qty = tracker.get_slot("quote_quantity")
        
        # --- LÓGICA DE LIMPIEZA ---
        product = str(raw_product)
        if 'product_name":' in product:
            product = product.split('":"')[1].replace('"}', '')
        elif 'quote_product":' in product:
            product = product.split('":"')[1].replace('"}', '')
        # --------------------------------

        # Precios base
        price_per_foot = 5.00  # DTF estándar
        if product and "uv" in product.lower():
            price_per_foot = 6.00  # UV DTF
        
        try:
            # Extraer largo en pulgadas (ej: "22x60" -> 60)
            match = re.search(r'x\s*(\d+)', str(size).lower())
            inches = float(match.group(1)) if match else 12.0
            
            # Lógica de Bundles de DTF
            length_int = int(inches)
            
            # Verificamos si es DTF estándar y si el largo está en el diccionario de bundles
            # Nota: DTF_BUNDLE_PRICES debe estar definido arriba en tu archivo
            if not "uv" in product.lower() and 'DTF_BUNDLE_PRICES' in globals() and length_int in DTF_BUNDLE_PRICES:
                unit_price = DTF_BUNDLE_PRICES[length_int]
            else:
                # Cálculo lineal si no es bundle o es UV
                unit_price = (inches / 12) * price_per_foot
            
            # Asegurar que qty sea un número
            quantity = float(qty) if qty else 1.0
            total = unit_price * quantity

            # --- MODIFICACIÓN PARA GRID JSON ---

            # 1. Preparamos el texto del mensaje (Sin los botones aquí)
            message_text = (
                f"📊 **Instant Quote:**\n"
                f"- Product: {product}\n"
                f"- Size: {size}\n"
                f"- Qty: {quantity:.0f}\n"
                f"------------------\n"
                f"💰 Unit Price: ${unit_price:.2f}\n"
                f"💵 **Total Estimate: ${total:.2f}**\n\n"
                f"Would you like to place this order now?"
            )

            # 2. Construimos el JSON para el Grid (Sin emojis en los títulos)
            custom_grid = {
                "type": "grid",
                "text": message_text,
                "options": [
                    {
                        "title": "Yes, Order Now",
                        "payload": "/create_order_dtf"
                    },
                    {
                        "title": "Just asking",
                        "payload": "/deny"
                    }
                ]
            }
            
            # 3. Enviamos el Grid a través de json_message
            dispatcher.utter_message(json_message=custom_grid)

        except Exception as e:
            print(f"Error Quote: {e}")
            dispatcher.utter_message(text="Sorry, I couldn't calculate that. Please try again with a size like '22x60'.")

        # Limpiamos los slots de cotización para la siguiente consulta
        return [
            SlotSet("quote_product", None), 
            SlotSet("quote_size", None), 
            SlotSet("quote_quantity", None)
        ]