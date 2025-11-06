# actions/actions.py
import requests
import re
from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet

# --- Constantes ---
PRODUCT_PRICES = {
    "dtf + heat press": 5.99,
    "6 pack t-shirts": 68.95,
    "12 pack t-shirts": 99.00,
    "dtf custom gang sheet": 5.00,
    "dtf gang sheet": 5.00,
    "uv dtf gang sheet": 6.00,
    "custom size uv dtf gang sheet": 12.00,
    "dtf fluorescent gang sheets": 10.00,
    "print by size": 2.50
}
PRODUCTS_REQUIRING_SIZE = [
    "dtf custom gang sheet",
    "dtf gang sheet",
    "uv dtf gang sheet",
    "custom size uv dtf gang sheet",
    "dtf fluorescent gang sheets"
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
        price = None
        response_text = ""

        if product_name:
            product_key = product_name.lower()
            if product_key in PRODUCT_PRICES:
                price = PRODUCT_PRICES[product_key]
                response_text = f"The price for {product_name} is ${price:.2f}."
                if product_key in ["dtf custom gang sheet", "dtf gang sheet"]:
                    response_text += " That's the starting price for the 22x12 size."
                elif product_key == "uv dtf gang sheet":
                    response_text += " That's the starting price for the 11x12 size."
            else:
                response_text = f"Sorry, I don't have a specific price for '{product_name}'. Can you try rephrasing?"
        
        elif sheet_size:
            if sheet_size == "22x12":
                price = 5.00
                response_text = f"A 22x12 DTF Gang Sheet starts at ${price:.2f}."
            elif sheet_size.startswith("22x"):
                 response_text = f"For {sheet_size} DTF sheets, the price depends on the exact size. For example, a 22x12 starts at $5.00."
            elif sheet_size == "11x12":
                price = 6.00
                response_text = f"A 11x12 UV DTF Gang Sheet starts at ${price:.2f}."
            elif sheet_size.startswith("11x"):
                response_text = f"For {sheet_size} UV DTF sheets, the price depends on the exact size. For example, a 11x12 starts at $6.00."
            else:
                 response_text = f"Sorry, I'm not sure about the price for {sheet_size}."
        else:
            custom_json = {
                "type": "buttons",
                "text": "Sure, what product are you looking for a price on?",
                "options": [
                    {"title": "DTF Gang Sheet", "payload": '/inform{{"product_name":"DTF Custom Gang Sheet"}}'},
                    {"title": "UV DTF Gang Sheet", "payload": '/inform{{"product_name":"UV DTF Gang Sheet"}}'},
                    {"title": "6 Pack T-Shirts", "payload": '/inform{{"product_name":"6 Pack T-Shirts"}}'},
                    {"title": "DTF + Heat Press", "payload": '/inform{{"product_name":"DTF + Heat Press"}}'}
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
        if "dtf sheet" in product_key: product_key = "dtf custom gang sheet"
        elif "uv sheet" in product_key: product_key = "uv dtf gang sheet"
        if product_key in PRODUCT_PRICES: return {"product_name": product_key.title()}
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
        return {"category": str(slot_value)}

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