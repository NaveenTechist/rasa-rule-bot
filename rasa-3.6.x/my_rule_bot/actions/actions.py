import os
import logging
import psycopg2
from dotenv import load_dotenv
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# 1. Setup Logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 2. Load Environment Variables from .env file
load_dotenv()

def get_db_connection():
    """ Helper function to connect to PostgreSQL using environment variables """
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=os.getenv("DB_PORT")
        )
        logger.info("Database connection established successfully.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected Error during DB connection: {e}")
        return None

class ActionFetchBalance(Action):
    def name(self) -> Text:
        return "action_fetch_balance"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        logger.info("Executing ActionFetchBalance...")

        # Get user inputs
        user_input = tracker.latest_message.get("text")

        # If user just clicked button intent
        if user_input == "/check_balance":
            dispatcher.utter_message(
                text="Please enter your BGL number to check your account balance."
            )
            return [SlotSet("bgl_no", bgl_no)]

        

        bgl_no = tracker.get_slot("bgl_no") or user_input.strip()

        try:
            conn = get_db_connection()

            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT balance 
                    FROM bgl_txn 
                    WHERE bgl_no = %s
                    """,
                    (bgl_no,)
                )

                result = cursor.fetchone()
                conn.close()

                if result:
                    balance = result[0]
                    response = (
                        f"Your account balance for BGL number {bgl_no} "
                        f"is ₹{balance}. Thank you for banking with us."
                    )
                    logger.info(f"Balance fetched for BGL: {bgl_no}")
                else:
                    response = (
                        f"We could not find any account with BGL number {bgl_no}. "
                        "Please check the number and try again."
                    )

            else:
                response = (
                    "We are currently unable to connect to the database. "
                    "Please try again later."
                )

            dispatcher.utter_message(text=response)

        except Exception as e:
            logger.error(f"Error in ActionFetchBalance: {e}")
            dispatcher.utter_message(
                text="Sorry, something went wrong while fetching your balance."
            )

        return []
        
class ActionAtmIssue(Action):
    def name(self) -> Text:
        return "action_atm_issue"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        logger.info("Executing ActionAtmIssue...")

        # Get the serial number from the user's messages
        serial_number = tracker.latest_message.get('text')

        # If the user just clicked the button, it sends '/atm_issues'
        # in that case, we should ask them for the number first.
        if serial_number == "/atm_issues":
            dispatcher.utter_message(text="Please provide your transaction serial number to look up the details.")
            return []

        try:
            # 1. Try to connect to the db
            conn = get_db_connection()
            
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT transaction_date,
                           transaction_time,
                           card_acceptor_term_location,
                           transaction_amount,
                           actual_transaction_amount
                    FROM atm_iss
                    WHERE transaction_serial_number = %s
                """, (serial_number,))

                result = cursor.fetchone()

                if result:
                    date, time, location, amount, actual_amount = result
                    response = (
                        f"Transaction {serial_number} was performed on {date} "
                        f"at {time} at location {location}. "
                        f"The requested amount was ₹{amount}, "
                        f"and the actual debited amount was ₹{actual_amount}."
                    )
                else:
                    response = f"No transaction found for the serial number {serial_number}."
                
                conn.close()
                logger.info(f"ATM query completed for serial: {serial_number}")
            else:
                response = f"Simulated Mode: Transaction {serial_number} recorded. (DB Offline)"
                logger.warning("DB Connection failed for ATM issue, falling back to simulated.")

            dispatcher.utter_message(text=response)
            
        except Exception as e:
            logger.error(f"Error in ActionAtmIssue.run: {e}")
            dispatcher.utter_message(text="I'm sorry, I couldn't process your ATM request right now.")
        
        return []
