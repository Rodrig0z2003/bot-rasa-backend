import requests
import re
import math
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, ConversationPaused

# --- ¡CONFIGURA ESTAS URLS! ---
#LARAVEL_WEBHOOK_URL = "http://localhost:8001/api/rasa-order"
LARAVEL_WEBHOOK_URL = "https://dev.gangsheet-builders.com/api/rasa-order"
#LARAVEL_UPLOAD_PAGE_URL = "http://localhost:8001/upload-order-file"
LARAVEL_UPLOAD_PAGE_URL = "https://dev.gangsheet-builders.com/upload-order-file"

# ---------------------------------

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
# NUEVA CLASE: PREGUNTAR CANTIDAD (DINÁMICO)
# -------------------------------------------------------------------------
class ActionAskQuantity(Action):
    def name(self) -> Text:
        return "action_ask_quantity"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Obtenemos AMBOS slots
        product = tracker.get_slot("product_name")
        subtype = tracker.get_slot("tshirt_subtype") # <--- ESTE ES EL IMPORTANTE

        # Normalizamos (quitamos espacios y ponemos minúsculas para comparar)
        check_val = ""
        if subtype:
            check_val = subtype.lower().strip()
        elif product:
            check_val = product.lower().strip()

        # LÓGICA DE MENSAJES (Usando 'in' para ser más flexible)
        
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
# CLASE 2: VALIDAR FORMULARIO DE PEDIDO
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

        # --- CASO 1: SERVICIOS DE ROPA (T-Shirts & Heat Press) ---
        # Agrupamos aquí todo lo que NO sea Gang Sheet (no necesita sheet_size ni custom_inches)
        if product in ["Customs T-Shirt", "Custom T-shirts", "DTF + Heat Press Service"]:
            
            # Solo "Customs T-Shirt" original requería el subtipo para elegir color/estilo
            if product == "Customs T-Shirt":
                if not subtype:
                    required.append("tshirt_subtype")
            
            # Una vez resuelto el subtipo, pedimos lo común. 
            # NO pedimos 'category' ni 'sheet_size'.
            required.extend(["quantity", "user_name", "user_email", "carrier"])
            return required

        # --- CASO 2: GANG SHEETS (DTF / UV) ---
        required.append("category")

        if category == "Print by size":
            # CAMINO A: Print by size (Quantity -> Inches)
            required.extend(["quantity", "custom_inches", "user_name", "user_email", "carrier"])
        else:
            # CAMINO B: Standard (Quantity -> Sheet Size)
            required.extend(["quantity", "sheet_size", "user_name", "user_email", "carrier"])

        return required

    def validate_product_name(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"product_name": str(slot_value)}

    def validate_tshirt_subtype(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        subtype = str(slot_value)
        # Actualizamos product_name para que sea específico (ej. "Black T-Shirt")
        return {"tshirt_subtype": subtype, "product_name": subtype}

    def validate_quantity(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        try:
            qty = float(slot_value)
            if qty < 1:
                dispatcher.utter_message(text="Quantity must be at least 1.")
                return {"quantity": None}
            return {"quantity": qty}
        except:
            dispatcher.utter_message(text="Please enter a valid number.")
            return {"quantity": None}

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

        # Calcular y mostrar precio estimado
        inches_int = int(inches)
        bundle_prices = globals().get('DTF_BUNDLE_PRICES', {})
        dtf_price = globals().get('DTF_PRICE_PER_FOOT', 5.00)
        uv_price = globals().get('UV_PRICE_PER_FOOT', 6.00)
        
        if inches_int in bundle_prices:
             price = bundle_prices[inches_int]
             dispatcher.utter_message(text=f"✅ Got it. {inches_int} inches. Special Bundle Price: **${price:.2f}**!")
        else:
            prod = tracker.get_slot("product_name")
            rate = uv_price if (prod and "uv" in prod.lower()) else dtf_price
            feet = inches / 12
            price = feet * rate
            dispatcher.utter_message(text=f"✅ Got it. {inches} inches is approx {feet:.1f} feet. Estimated price: **${price:.2f}**.")
        
        return {"custom_inches": inches}

    def validate_category(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        cat = str(slot_value).lower()
        product = tracker.get_slot("product_name")
        if "print" in cat: return {"category": "Print by size"}
        if product and "uv" in product.lower(): return {"category": "UV DTF Gang Sheet"}
        return {"category": "DTF Gang Sheet"}

    def validate_sheet_size(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"sheet_size": str(slot_value)}
        
    def validate_user_name(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        name = str(slot_value).strip()
        if name.lower() in ["stop", "cancel"]:
             dispatcher.utter_message(text="OK, cancelling order.")
             return {"user_name": None, "requested_slot": None}
        return {"user_name": name.title()}

    def validate_user_email(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"user_email": str(slot_value)}

    def validate_carrier(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"carrier": str(slot_value)}


# -------------------------------------------------------------------------
# CLASE 3: ENVIAR A LARAVEL API (Con Uploader para todos)
# -------------------------------------------------------------------------
class ActionSubmitOrderToApi(Action):
    def name(self) -> Text:
        return "action_submit_order_to_api"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # 1. OBTENER DATOS
        category = tracker.get_slot("category")
        custom_inches = tracker.get_slot("custom_inches")
        sheet_size = tracker.get_slot("sheet_size")
        quantity = tracker.get_slot("quantity")
        
        # Obtener nombres crudos
        product_generic = tracker.get_slot("product_name")
        subtype = tracker.get_slot("tshirt_subtype")
        
        # 2. LIMPIEZA DEL NOMBRE (REGEX CORREGIDO Y AGRESIVO)
        # Prioridad: Subtipo (Camisetas) > Genérico
        raw_name = subtype if subtype else product_generic
        final_product_name = str(raw_name) # Asegurar que es string

        # Si detectamos formato JSON de Rasa (/inform{...}), extraemos lo de adentro
        if "{" in final_product_name and ":" in final_product_name:
            match = re.search(r':"([^"]+)"', final_product_name)
            if match:
                final_product_name = match.group(1) # Extrae: Custom T-shirts
        
        # Limpieza extra por si quedan comillas o llaves
        final_product_name = final_product_name.replace('"}', '').replace('"', '').strip()


        # 3. LÓGICA DE TAMAÑO (SIZE) - ORDEN CORREGIDO
        # El error antes era filtrar por nombre. Ahora filtramos por DATOS.
        
        final_size_str = "N/A (Apparel/Service)" # Valor por defecto (para Polos)

        # A. ¿Es Print by Size? (Prioridad 1)
        if category == "Print by size" and custom_inches:
            final_size_str = f"{custom_inches} Inches (Custom)"
            
        # B. ¿Tiene un sheet_size definido? (Prioridad 2 - DTF y UV Estándar)
        # ESTO CORRIGE EL DTF. Si sheet_size existe (ej: 22x12), LO USA, 
        # sin importar si el nombre dice "Custom".
        elif sheet_size:
            final_size_str = sheet_size

        # C. Si no es ninguno de los anteriores, se queda como "N/A (Apparel/Service)"
            
        # 4. PREPARAR DATOS
        order_data = {
            "product": final_product_name, 
            "category": category if category else "Apparel",
            "quantity": quantity,
            "size": final_size_str,
            "customer_name": tracker.get_slot("user_name"),
            "customer_email": tracker.get_slot("user_email"),
            "shipping_method": tracker.get_slot("carrier"),
            "sender_id": tracker.sender_id
        }

        dispatcher.utter_message(text="Perfect! Submitting your order details...")

        # 5. ENVIAR A LARAVEL
        try:
            response = requests.post(LARAVEL_WEBHOOK_URL, json=order_data)
            response.raise_for_status()
            order_id = response.json().get("order_id")
            
            if order_id:
                link = f"{LARAVEL_UPLOAD_PAGE_URL}/{order_id}"
                dispatcher.utter_message(text=f"Success! Your order #{order_id} has been created.")
                dispatcher.utter_message(text=f"**IMPORTANT:** Please upload your design file using this link:\n[Click here to upload design]({link})")
                dispatcher.utter_message(text=f"A confirmation email was sent to {order_data['customer_email']}.")
            else:
                dispatcher.utter_message(text="Order created successfully. Check your email.")
        
        except Exception as e:
            dispatcher.utter_message(text=f"Error submitting order: {e}")

        # Reseteamos slots
        return [SlotSet(s, None) for s in ["product_name", "quantity", "sheet_size", "category", "user_name", "user_email", "carrier", "custom_inches", "tshirt_subtype"]]
# -------------------------------------------------------------------------
# OTRAS CLASES (Cancelación, Hand-off)
# -------------------------------------------------------------------------

class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="OK, I've cancelled this order. What can I help you with next?")
        return [SlotSet(slot, None) for slot in ["product_name", "quantity", "sheet_size", "category", "user_name", "user_email", "carrier", "custom_inches", "tshirt_subtype"]]


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
            webhook_url = "https://dev.gangsheet-builders.com/api/live-chat-request"
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
            webhook_url = "https://dev.gangsheet-builders.com/api/live-chat-request"
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