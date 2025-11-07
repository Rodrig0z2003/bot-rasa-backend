# actions/actions.py
import requests
import re
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet

# --- Constantes ---
# Precios para UV DTF Gang Sheets (11x...)
# Regla: 11x12 = $6, 11x24 = $12 ... 11x300 = $150
UV_PRICES = {
    "11x12": 6.00, "11x24": 12.00, "11x36": 18.00, "11x48": 24.00, "11x60": 30.00,
    "11x72": 36.00, "11x84": 42.00, "11x96": 48.00, "11x108": 54.00, "11x120": 60.00,
    "11x132": 66.00, "11x144": 72.00, "11x156": 78.00, "11x168": 84.00, "11x180": 90.00,
    "11x192": 96.00, "11x204": 102.00, "11x216": 108.00, "11x228": 114.00, "11x240": 120.00,
    "11x252": 126.00, "11x264": 132.00, "11x276": 138.00, "11x288": 144.00, "11x300": 150.00
}
# Precios para DTF Gang Sheets (22x...)
# Regla: 22x12 = $5, 22x24 = $10 ... 22x300 = $105 (5 * 21 tamaños)
DTF_PRICES = {
    "22x12": 5.00, "22x24": 10.00, "22x36": 15.00, "22x48": 20.00, "22x60": 25.00,
    "22x72": 30.00, "22x84": 35.00, "22x96": 40.00, "22x120": 45.00, "22x132": 50.00,
    "22x144": 55.00, "22x156": 60.00, "22x168": 65.00, "22x180": 70.00, "22x192": 75.00,
    "22x204": 80.00, "22x216": 85.00, "22x238": 90.00, "22x274": 95.00, "22x286": 100.00,
    "22x300": 105.00
}
# Lista de productos que NECESITAN un tamaño
# (Basado en tu imagen de categorías)
PRODUCTS_REQUIRING_SIZE = [
    "dtf fluorescent gang sheets",
    "uv dtf gang sheet",
    "dtf gang sheet",
    "print by size",
    "custom size uv dtf gang sheet",
    "custom size dtf gang sheet",
    "dtf custom gang sheet" # (Antiguo nombre, por si acaso)
]

# Lista de slots del formulario (SIN file_url)
FORM_SLOTS = [
    "product_name", 
    "quantity", 
    "sheet_size", 
    "category",
    "user_name",
    "user_email",
    "carrier"
]

# --- ¡CONFIGURA ESTAS URLS! ---
# URL de tu Webhook en Laravel
#LARAVEL_WEBHOOK_URL = "https://72.60.24.115/api/rasa-order" # <-- ¡USA TU IP O DOMINIO!
#LARAVEL_WEBHOOK_URL = "http://localhost:8001/api/rasa-order" # <-- ¡Puerto 8001!

LARAVEL_WEBHOOK_URL = "https://dev.gangsheet-builders.com/api/rasa-order"

# URL base para tu página de subida de archivos
#LARAVEL_UPLOAD_PAGE_URL = "https://72.60.24.115/upload-order-file" # <-- ¡USA TU IP O DOMINIO!
#LARAVEL_UPLOAD_PAGE_URL = "http://localhost:8001/upload-order-file" # <-- ¡Puerto 8001!

LARAVEL_UPLOAD_PAGE_URL = "https://dev.gangsheet-builders.com/upload-order-file"
# ---------------------------------


class ActionGetPrice(Action):
    def name(self) -> Text:
        return "action_get_price"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        sheet_size = tracker.get_slot("sheet_size")
        product_name = tracker.get_slot("product_name")
        response_text = ""

        if sheet_size:
            # El usuario preguntó por un tamaño específico
            if sheet_size in DTF_PRICES:
                price = DTF_PRICES[sheet_size]
                response_text = f"A **{sheet_size} DTF Gang Sheet** (for fabrics) costs **${price:.2f}**."
            elif sheet_size in UV_PRICES:
                price = UV_PRICES[sheet_size]
                response_text = f"A **{sheet_size} UV DTF Gang Sheet** (for hard surfaces) costs **${price:.2f}**."
            else:
                response_text = f"Sorry, I don't have an exact price for the size '{sheet_size}'. Can you select from the list?"

        elif product_name:
            # El usuario preguntó por un producto
            product_key = product_name.lower()
            if "uv" in product_key:
                response_text = f"Prices for **{product_name}** start at **$6.00** for the **11x12** size and go up to $150.00 for the 11x300."
            elif "dtf" in product_key or "fluorescent" in product_key:
                response_text = f"Prices for **{product_name}** start at **$5.00** for the **22x12** size and go up to $105.00 for the 22x300."
            elif "t-shirt" in product_key:
                 response_text = "A 6 Pack of T-Shirts is $68.95 and a 12 Pack is $99.00."
            else:
                response_text = f"Sorry, I don't have a specific price for '{product_name}'. Can you try rephrasing?"

        else:
            # El usuario solo dijo "cuánto cuesta"
            custom_json = {
                "type": "grid",
                "text": "Sure, what product are you looking for a price on?",
                "options": [
                    {"title": "DTF Gang Sheet (22x...)", "payload": '/inform{{"product_name":"DTF Custom Gang Sheet"}}'},
                    {"title": "UV DTF Gang Sheet (11x...)", "payload": '/inform{{"product_name":"UV DTF Gang Sheet"}}'},
                    {"title": "T-Shirt Packs", "payload": '/inform{{"product_name":"6 Pack T-Shirts"}}'}
                ]
            }
            dispatcher.utter_message(json_message=custom_json)
            return []

        dispatcher.utter_message(text=response_text)
        return []


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
        """Define dinámicamente qué slots se requieren."""
        
        required = [
            "product_name",
            "category",
            "quantity"
        ]
        
        product_name = tracker.get_slot("product_name")

        if product_name and product_name.lower() in PRODUCTS_REQUIRING_SIZE:
            if "sheet_size" not in required:
                try:
                    quantity_index = required.index("quantity")
                    required.insert(quantity_index + 1, "sheet_size")
                except ValueError:
                    required.append("sheet_size")

        required.extend([
            "user_name",
            "user_email",
            "carrier"
        ])
        
        # Filtra los slots que ya están llenos
        return [slot for slot in required if tracker.get_slot(slot) is None]

    def validate_product_name(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        product_key = str(slot_value).lower()

        # Lista de productos válidos que se pueden pedir
        # (Quitamos 'dtf + heat press' y '6 pack t-shirts' del formulario, como pediste)
        valid_products = [
            "dtf custom gang sheet", "dtf gang sheet", "uv dtf gang sheet",
            "custom size uv dtf gang sheet", "dtf fluorescent gang sheets",
            "print by size"
        ]

        # Redireccionamos sinónimos
        if "dtf sheet" in product_key and "uv" not in product_key: 
            product_key = "dtf custom gang sheet"
        elif "uv sheet" in product_key: 
            product_key = "uv dtf gang sheet"

        if product_key in valid_products:
            return {"product_name": product_key.title()}
        else:
            # Si eligieron uno que ya no está en el formulario (como T-Shirts)
            if "t-shirt" in product_key or "heat press" in product_key:
                dispatcher.utter_message(text=f"Sorry, I can only create orders for Gang Sheets. For T-Shirts or Heat Press services, please contact us directly.")
            else:
                dispatcher.utter_message(text=f"Sorry, I don't recognize the product '{slot_value}'.")
            return {"product_name": None}

    def validate_quantity(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        try:
            quantity = float(slot_value)
            if quantity <= 0: raise ValueError
        except (TypeError, ValueError):
            dispatcher.utter_message(text="Please enter a valid quantity (like 1, 5, or 10).")
            return {"quantity": None}
        return {"quantity": quantity}

    def validate_sheet_size(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"sheet_size": str(slot_value)}
        
    def validate_category(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"category": str(slot_wvalue)}

    def validate_user_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Valida el nombre (acepta cualquier cosa)."""
        name = str(slot_value).strip()
        
        # Si el usuario escribe "stop" o "cancel", detenemos
        if name.lower() in ["stop", "cancel"]:
            dispatcher.utter_message(text="OK, I've cancelled this order.")
            return {"user_name": None, "requested_slot": None, "carrier": None, "product_name": None, "category": None, "quantity": None, "sheet_size": None, "user_email": None}

        # Aceptamos cualquier otro texto como un nombre
        if not name:
            dispatcher.utter_message(text="Please enter a name.")
            return {"user_name": None}
            
        return {"user_name": name.title()}

    def validate_user_email(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        email = str(slot_value)
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            dispatcher.utter_message(text="That doesn't look like a valid email address. Please try again.")
            return {"user_email": None}
        return {"user_email": email}

    def validate_carrier(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return {"carrier": str(slot_value)}


class ActionSubmitOrderToApi(Action):
    def name(self) -> Text:
        return "action_submit_order_to_api"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        dispatcher.utter_message(text="Perfect! Submitting your order details to create a confirmation...")

        order_data = {
            "product": tracker.get_slot("product_name"),
            "category": tracker.get_slot("category"),
            "quantity": tracker.get_slot("quantity"),
            "size": tracker.get_slot("sheet_size"),
            "customer_name": tracker.get_slot("user_name"),
            "customer_email": tracker.get_slot("user_email"),
            "shipping_method": tracker.get_slot("carrier"),
            "sender_id": tracker.sender_id
        }

        try:
            # ¡Importante! 'verify=False' es solo para pruebas si tienes problemas de SSL
            # En producción, deberías tener un certificado SSL válido
            response = requests.post(LARAVEL_WEBHOOK_URL, json=order_data)
            
            response.raise_for_status() # Lanza un error si la respuesta es 4xx o 5xx

            # Asumimos que Laravel responde con 200 o 201
            order_id = response.json().get("order_id")
            
            if order_id:
                upload_link = f"{LARAVEL_UPLOAD_PAGE_URL}/{order_id}"
                
                dispatcher.utter_message(text=f"Success! Your order confirmation is #{order_id}.")
                dispatcher.utter_message(text=f"**IMPORTANT:** Please upload your print file for order #{order_id} using this link:\n[Click here to upload your file]({upload_link})")
                dispatcher.utter_message(text=f"A confirmation has also been sent to {order_data['customer_email']}.")
            else:
                dispatcher.utter_message(text=f"Success! Your order is confirmed. Please check your email at {order_data['customer_email']} for instructions on how to upload your file.")

        except requests.exceptions.HTTPError as err:
            # Error de Laravel (4xx, 5xx)
            dispatcher.utter_message(text=f"Sorry, there was an error submitting your order (Code: {err.response.status_code}). Please contact support.")
        except requests.exceptions.ConnectionError:
            # Error de conexión (Rasa no puede encontrar a Laravel)
            dispatcher.utter_message(text="Sorry, I can't connect to the ordering system right now. Please try again in a few minutes.")
        except Exception as e:
            # Otro error
            dispatcher.utter_message(text=f"An unknown error occurred: {e}")

        return [SlotSet(slot, None) for slot in FORM_SLOTS]


class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="OK, I've cancelled this order. What can I help you with next?")
        return [SlotSet(slot, None) for slot in FORM_SLOTS]


class ActionAskSheetSize(Action):
    def name(self) -> Text:
        return "action_ask_sheet_size"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        product_name = tracker.get_slot("product_name")
        category = tracker.get_slot("category")

        # Decidimos qué lista de tallas mostrar
        # Por defecto, mostramos las tallas de DTF (22x...)
        utter_action = "utter_ask_sheet_size_dtf"

        # Si el producto O la categoría tiene "UV", mostramos las tallas UV (11x...)
        if product_name and "uv" in product_name.lower():
            utter_action = "utter_ask_sheet_size_uv"
        elif category and "uv" in category.lower():
            utter_action = "utter_ask_sheet_size_uv"

        dispatcher.utter_message(response=utter_action)
        return []