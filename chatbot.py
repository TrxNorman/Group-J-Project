import configparser
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, CallbackContext)
import requests

# HKBU chatbot configuration
class HKBU_ChatGPT():
	def __init__(self,config_='./config.ini'):
		if type(config_) == str:
			self.config = configparser.ConfigParser()
			self.config.read(config_)
		elif type(config_) == configparser.ConfigParser:
			self.config = config_

	def submit(self,message):
		conversation = [{"role": "user", "content": message}]
		url = (self.config['CHATGPT']['BASICURL']) + "/deployments/" + (self.config['CHATGPT']['MODELNAME']) + "/chat/completions/?api-version=" + (self.config['CHATGPT']['APIVERSION'])

		headers = { 'Content-Type': 'application/json',
		'api-key': (self.config['CHATGPT']['ACCESS_TOKEN']) }
		payload = { 'messages': conversation }
		response = requests.post(url, json=payload, headers=headers)
		if response.status_code == 200:
			data = response.json()
			return data['choices'][0]['message']['content']
		else:
			return 'Error:', response

# Global state to track bot mode
job_search_mode = False  # By default, bot is not in job search mode
def find_job(update: Update, context: CallbackContext) -> None:
    global job_search_mode
    job_search_mode = True  # Activate job search mode
    update.message.reply_text(
        "Please provide your job requirements: experience (in years), salary(minimal value is 55000HKD per month), location(The city or area where the job is located), country, position(Job's name)."
        "(Example: experience: 5, salary: 60000). Type 'exit' to exit job search mode."
    )

def handle_user_input(update: Update, context: CallbackContext) -> None:
    global job_search_mode

    if job_search_mode:  # Process job-related inputs only if in job search mode
        user_input = update.message.text.strip()

        # Exit job search mode
        if user_input.lower() == 'exit':
            job_search_mode = False
            update.message.reply_text("Exiting job recommendation mode. You can chat normally now.")
            return

        # Process job requirements
        filters = {}
        for item in user_input.split(','):
            key_value = item.strip().split(':')
            if len(key_value) == 2:
                filters[key_value[0].strip().lower()] = key_value[1].strip()

        # Query Firebase database
        jobs_ref = db.collection('job_descriptions')
        results = []

        for doc in jobs_ref.stream():
            job_data = doc.to_dict()
            # Apply filters
            if 'location' in filters:
                if filters['location'].lower() != job_data.get('location', '').lower():
                    continue
            if 'country' in filters:
                if filters['country'].lower() != job_data.get('Country', '').lower():
                    continue
            if 'position' in filters:
                if filters['position'].lower() != job_data.get('Role', '').lower():
                    continue
            if 'experience' in filters:
                user_exp = int(filters['experience'])
                experience_range = job_data['Experience'].lower().replace('years', '').strip()
                min_exp, max_exp = map(int, experience_range.split(' to '))
                if not (min_exp <= user_exp <= max_exp):
                    continue
            if 'salary' in filters:
                user_salary = int(filters['salary'])
                salary_range = job_data['Salary Range'].replace('$', '').replace('K', '000').strip()
                min_sal, max_sal = map(int, salary_range.split('-'))
                if not (min_sal <= user_salary <= max_sal):
                    continue

            results.append(job_data)
            if len(results) >= 5:
                break

        # Respond to user with job results
        if results:
            response_message = "Based on your requirements, here are some positions:\n\n"
            for job in results:
                response_message += (
                    f"Position: {job['Role']}\n"
                    f"Company: {job['Company']}\n"
                    f"Location: {job['location']}\n"
                    f"Experience requirement: {job['Experience']}\n"
                    f"Salary Range: {job['Salary Range']}\n"
                    f"Responsibilities: {job['Responsibilities']}\n"
                    f"Contact Person: {job['Contact Person']}\n"
                    f"Contact: {job['Contact']}\n"
                    "--------------------------\n"
                )
        else:
            response_message = "Sorry, no matching jobs found."

        update.message.reply_text(response_message)
    else:
        # Default to ChatGPT logic when not in job search mode
        equiped_chatgpt(update, context)

def equiped_chatgpt(update: Update, context):
    global chatgpt
    reply_message = chatgpt.submit(update.message.text)
    context.bot.send_message(chat_id=update.effective_chat.id, text=reply_message)

def main():
    config = configparser.ConfigParser()
    config.read('config.ini')

    # Init Firebase
    cred = credentials.Certificate(config['FIREBASE']['SERVICE_ACCOUNT_KEY_PATH'])
    firebase_admin.initialize_app(cred)
    global db
    db = firestore.client()

    # Init Telegram Bot
    updater = Updater(token=(config['TELEGRAM']['ACCESS_TOKEN']), use_context=True)
    dispatcher = updater.dispatcher

    # Init ChatGPT 
    global chatgpt
    chatgpt = HKBU_ChatGPT(config)

    
    dispatcher.add_handler(CommandHandler("find_job", find_job))
    dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), handle_user_input))

    
    try:
        print("Bot is starting...")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        print(f"Error starting bot: {e}")

if __name__ == '__main__':
	main()
