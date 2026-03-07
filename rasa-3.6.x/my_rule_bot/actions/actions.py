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
                    "We are currently unable to connect to the database."
                    "Please try again later."
                )

            dispatcher.utter_message(text=response)
            dispatcher.utter_message(response="utter_main_menu")

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
            dispatcher.utter_message(response="utter_main_menu")
            
        except Exception as e:
            logger.error(f"Error in ActionAtmIssue.run: {e}")
            dispatcher.utter_message(text="I'm sorry, I couldn't process your ATM request right now.")
        
        return []


class ActionATMFail(Action):

    def name(self):
        """
        Name of the custom action used in domain.yml
        """
        return "action_atm_fail"

    def run(self, dispatcher, tracker, domain):

        try:
            # -----------------------------
            # Get database connection
            # -----------------------------
            conn = get_db_connection()
            cursor = conn.cursor()

            logger.info("Connected to database successfully")

            # ---------------------------------------------
            # SQL Query
            # Fetch only failed ATM transactions
            # Condition:
            # actual_transaction_amount = 0.00
            # ---------------------------------------------
            query = """
                SELECT 
                    transaction_serial_number,
                    transaction_date,
                    card_acceptor_term_location,
                    transaction_amount,
                    actual_transaction_amount
                FROM atm_iss
                WHERE actual_transaction_amount = 0.00
                ORDER BY transaction_date DESC
                LIMIT 5
            """

            cursor.execute(query)

            results = cursor.fetchall()

            logger.info(f"Number of failed transactions found: {len(results)}")

            # ---------------------------------------------
            # If no failed transactions found
            # ---------------------------------------------
            if not results:
                dispatcher.utter_message(
                    text="No failed ATM transactions were found."
                )
            else:

                dispatcher.utter_message(
                    text="Here are the top 5 failed ATM transactions:"
                )

                # Loop through records and display them
                for row in results:

                    serial_number = row[0]
                    date = row[1]
                    location = row[2]
                    transaction_amount = row[3]

                    message = (
                        f"Transaction Serial Number: {serial_number}\n"
                        f"Transaction Date: {date}\n"
                        f"ATM Location: {location}\n"
                        f"Transaction Amount: {transaction_amount}\n"
                        f"Status: FAILED"
                    )

                    dispatcher.utter_message(text=message)

            # Close DB resources
            cursor.close()
            conn.close()

            logger.info("Database connection closed")

        except Exception as e:

            # Log the error for debugging
            logger.error(f"Error fetching ATM failed transactions: {str(e)}")

            dispatcher.utter_message(
                text="Sorry, I couldn't retrieve ATM failed transaction details at the moment."
            )

        # Return to main menu
        dispatcher.utter_message(response="utter_main_menu")

        return []

class ActionATMSuccess(Action):

    def name(self):
        return "action_atm_success"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message(text="Fetching successful ATM transaction details...")
        dispatcher.utter_message(response="utter_main_menu")
        return []


class ActionBGLFetch(Action):

    def name(self):
        return "action_bgl_fetch"

    def run(self, dispatcher, tracker, domain):

        rrn = tracker.latest_message.get("text")

        dispatcher.utter_message(text=f"Fetching BGL details for RRN: {rrn}")
        dispatcher.utter_message(response="utter_main_menu")    
        return []