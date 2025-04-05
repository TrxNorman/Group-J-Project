import os
import json
import requests
from flask import Flask, request
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import secretmanager

# initialize GCP Secret Manager
secret_client = secretmanager.SecretManagerServiceClient()
project_id = "level-research-455706-i4"  


def access_secret_version(secret_id, version_id="latest"):
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


# get secrets from GCP Secret Manager
telegram_token = access_secret_version("TELEGRAM_TOKEN")
firebase_credential_json = access_secret_version("FIREBASE_CREDENTIAL_JSON")
access_token = access_secret_version("ACCESS_TOKEN")

# initial Firebase
firebase_credentials = json.loads(firebase_credential_json)
cred = credentials.Certificate(firebase_credentials)
firebase_admin.initialize_app(cred)
db = firestore.client()

# initial Flask
app = Flask(__name__)

# ChatGPT 
class HKBU_ChatGPT():
    def __init__(self):
        self.chatgpt_url = "https://genai.hkbu.edu.hk/general/rest"
        self.chatgpt_model = "gpt-4-o-mini"
        self.chatgpt_version = "2024-05-01-preview"
        self.chatgpt_key = access_token

    def submit(self, message):
        url = f"{self.chatgpt_url}/deployments/{self.chatgpt_model}/chat/completions/?api-version={self.chatgpt_version}"
        headers = {
            'Content-Type': 'application/json',
            'api-key': self.chatgpt_key
        }
        payload = {'messages': [{"role": "user", "content": message}]}
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return "ChatGPT Error"

chatgpt = HKBU_ChatGPT()
job_search_mode = {}  # Dictionary to track job search mode for each user


@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" not in data:
        return "ignored", 200

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    if text.strip().lower() == "/find_job":
        job_search_mode[chat_id] = True
        send_message(chat_id, (
            "Please provide your job requirements\n"
            "1. Experience (in years)\n"
            "2. Salary (minimal value is 55000HKD per month)\n"
            "3. Location (The city or area where the job is located)\n"
            "4. Country\n"
            "5. Position (Job's name)\n"
            "(Example: experience: 5, salary: 60000)\n"
            "Type 'exit' to exit job search mode."
        ))
        return "ok", 200

    if job_search_mode.get(chat_id):
        if text.strip().lower() == 'exit':
            job_search_mode[chat_id] = False
            send_message(chat_id, "Exiting job recommendation mode. You can chat normally now.")
            return "ok", 200

        filters = {}
        for item in text.split(','):
            key_value = item.strip().split(':')
            if len(key_value) == 2:
                filters[key_value[0].strip().lower()] = key_value[1].strip()

        jobs_ref = db.collection('job_descriptions')
        results = []

        for doc in jobs_ref.stream():
            job = doc.to_dict()
            if 'location' in filters and filters['location'].lower() != job.get('location', '').lower():
                continue
            if 'country' in filters and filters['country'].lower() != job.get('Country', '').lower():
                continue
            if 'position' in filters and filters['position'].lower() != job.get('Role', '').lower():
                continue
            if 'experience' in filters:
                try:
                    user_exp = int(filters['experience'])
                    exp_range = job['Experience'].lower().replace('years', '').strip()
                    min_exp, max_exp = map(int, exp_range.split(' to '))
                    if not (min_exp <= user_exp <= max_exp):
                        continue
                except:
                    continue
            if 'salary' in filters:
                try:
                    user_salary = int(filters['salary'])
                    sal_range = job['Salary Range'].replace('$', '').replace('K', '000').strip()
                    min_sal, max_sal = map(int, sal_range.split('-'))
                    if not (min_sal <= user_salary <= max_sal):
                        continue
                except:
                    continue

            results.append(job)
            if len(results) >= 5:
                break

        if results:
            msg = "Here are some job matches:\n\n"
            for job in results:
                msg += (
                    f"Position: {job['Role']}\n"
                    f"Company: {job['Company']}\n"
                    f"Location: {job['location']}\n"
                    f"Experience: {job['Experience']}\n"
                    f"Salary: {job['Salary Range']}\n"
                    f"Responsibilities: {job['Responsibilities']}\n"
                    f"Contact: {job['Contact Person']} ({job['Contact']})\n"
                    "------------------------\n"
                )
        else:
            msg = "Sorry, no matching jobs found."

        send_message(chat_id, msg)
        return "ok", 200


    reply = chatgpt.submit(text)
    send_message(chat_id, reply)
    return "ok", 200


def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))