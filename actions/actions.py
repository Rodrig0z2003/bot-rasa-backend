# actions/actions.py (V11.0 - Inteligente y con limpieza de memoria)

from typing import Any, Text, Dict, List, Optional
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet # <--- ¡IMPORTANTE! IMPORTAR SlotSet

# --- Precios de Productos ---
PRODUCT_PRICES = {
    "dtf + heat press": 5.99,
    "6 pack t-shirts": 68.95,
    "12 pack t-shirts": 99.00,
    "dtf custom gang sheet": 5.00, # Precio base
    "dtf gang sheet": 5.00, # Precio base
    "uv dtf gang sheet": 6.00, # Precio base
    "custom size uv dtf gang sheet": 12.00,
    "dtf fluorescent gang sheets": 10.00,
    "print by size": 2.50
}

# Productos que requieren un tamaño
PRODUCTS_REQUIRING_SIZE = [
    "dtf custom gang sheet",
    "dtf gang sheet",
    "uv dtf gang sheet",
    "custom size uv dtf gang sheet",
    "dtf fluorescent gang sheets"
]

# Slots que deben limpiarse
FORM_SLOTS = ["product_name", "quantity", "sheet_size"]


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
            # CORREGIDO: Usar el formato title/payload que tu Vue espera
            custom_json = {
                "type": "buttons",
                "text": "Sure, what product are you looking for a price on?",
                "options": [
                    {"title": "DTF Gang Sheet", "payload": '/inform{"product_name":"DTF Custom Gang Sheet"}'},
                    {"title": "UV DTF Gang Sheet", "payload": '/inform{"product_name":"UV DTF Gang Sheet"}'},
                    {"title": "6 Pack T-Shirts", "payload": '/inform{"product_name":"6 Pack T-Shirts"}'},
                    {"title": "DTF + Heat Press", "payload": '/inform{"product_name":"DTF + Heat Press"}'}
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
        product_name = tracker.get_slot("product_name")

        if product_name and product_name.lower() in PRODUCTS_REQUIRING_SIZE:
            return ["product_name", "sheet_size", "quantity"]
        else:
            return ["product_name", "quantity"]

    def validate_product_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Valida que el producto exista en nuestra lista de precios."""
        
        product_key = str(slot_value).lower()

        # Lógica de sinónimos
        if "dtf sheet" in product_key or "custom gang sheet" in product_key or product_key == "dtf":
            product_key = "dtf custom gang sheet"
        elif "uv sheet" in product_key or "uv gang" in product_key or product_key == "uv dtf":
            product_key = "uv dtf gang sheet"

        if product_key in PRODUCT_PRICES:
            return {"product_name": product_key.title()}
        else:
            dispatcher.utter_message(text=f"Sorry, I don't recognize the product '{slot_value}'. Please select one from the list.")
            return {"product_name": None}

    def validate_quantity(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Valida la cantidad."""
        product_name = tracker.get_slot("product_name")
        try:
            quantity = int(slot_value)
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            dispatcher.utter_message(text="Please enter a valid quantity (like 1, 5, or 10).")
            return {"quantity": None}

        if product_name and product_name.lower() == "dtf + heat press":
            if quantity < 24:
                dispatcher.utter_message(text=f"Sorry, our 'DTF + Heat Press' service has a minimum order of 24 pieces. You selected {quantity}.")
                return {"quantity": None}
        
        return {"quantity": quantity}

    def validate_sheet_size(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Valida que el tamaño del sheet sea correcto."""
        size = str(slot_value).lower()
        product_name = tracker.get_slot("product_name")

        if "uv" in product_name.lower():
            if not size.startswith("11x"):
                dispatcher.utter_message(text=f"That doesn't look like a valid UV size. UV sizes start with '11x' (e.g., '11x12', '11x24').")
                return {"sheet_size": None}
        else:
            if not size.startswith("22x"):
                dispatcher.utter_message(text=f"That doesn't look like a valid DTF size. DTF sizes start with '22x' (e.g., '22x12', '22x36').")
                return {"sheet_size": None}
        
        return {"sheet_size": size}


class ActionSubmitOrderToApi(Action):
    def name(self) -> Text:
        return "action_submit_order_to_api"
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        product = tracker.get_slot("product_name")
        quantity = tracker.get_slot("quantity")
        size = tracker.get_slot("sheet_size")

        # --- AQUÍ ES DONDE LLAMARÍAS A TU WEBHOOK DE LARAVEL ---
        
        if size:
            dispatcher.utter_message(text=f"OK! I have submitted your order for {quantity} x {product} (Size: {size}). (This is a custom action).")
        else:
            dispatcher.utter_message(text=f"OK! I have submitted your order for {quantity} x {product}. (This is a custom action).")

        # --- ¡LA CORRECCIÓN MÁS IMPORTANTE! ---
        # Limpia los slots usando SlotSet para el próximo pedido
        return [SlotSet(slot, None) for slot in FORM_SLOTS]

# --- ¡NUEVA ACCIÓN PARA CANCELAR! ---
class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="OK, I've cancelled this order. What can I help you with next?")
        
        # Limpia los slots
        return [SlotSet(slot, None) for slot in FORM_SLOTS]