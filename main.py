from dotenv import load_dotenv
load_dotenv()
import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

# --- API KEYS ---
GROQ_KEY = "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"
HINDSIGHT_KEY = "hsk_3f70dd496f237781c2c47f420c192105_73282700529be00d"
HINDSIGHT_BASE = "https://api.hindsight.vectorize.io"
BANK_ID = "codesensei"

# --- SETUP ---
app = FastAPI()
groq_client = Groq(api_key=GROQ_KEY)

# --- HINDSIGHT HEADERS ---
def hs_headers():
    return {
        "Authorization": f"Bearer {HINDSIGHT_KEY}",
        "Content-Type": "application/json"
    }

# --- CREATE BANK ON STARTUP ---
try:
    requests.post(f"{HINDSIGHT_BASE}/banks", json={"bank_id": BANK_ID, "name": "CodeSensei"}, headers=hs_headers())
except:
    pass

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATA FORMAT ---
class SubmitRequest(BaseModel):
    code: str
    language: str
    mentor: str
    user_id: str

# --- MAIN ENDPOINT ---
@app.post("/submit")
async def submit_code(req: SubmitRequest):
    try:
        # 1. recall past mistakes
        recall_res = requests.post(
            f"{HINDSIGHT_BASE}/banks/{BANK_ID}/recall",
            json={"query": f"What has user {req.user_id} struggled with?"},
            headers=hs_headers()
        )
        results = recall_res.json().get("results", [])
        past_mistakes = "\n".join([r.get("text", "") for r in results]) or "No past mistakes yet."

        # 2. build prompt
        prompt = f"""
You are {req.mentor}. Stay completely in character the entire time.
This student previously struggled with: {past_mistakes}

Now review their {req.language} code:
{req.code}

If the code is wrong: roast them in your character's voice, explain the mistake clearly, give a hint without giving the answer away.
If the code is correct: hype them up in your character's voice.
Keep your response under 4 sentences. Stay in character the whole time.
"""

        # 3. get groq response
        chat = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        feedback = chat.choices[0].message.content

        # 4. save to hindsight memory
        requests.post(
            f"{HINDSIGHT_BASE}/banks/{BANK_ID}/retain",
            json={"content": f"User {req.user_id} practiced {req.language}. Mentor was {req.mentor}. Feedback: {feedback}"},
            headers=hs_headers()
        )

        return {"feedback": feedback, "mentor": req.mentor}

    except Exception as e:
        print(f"ERROR: {e}")
        return {"error": str(e)}

@app.get("/question/{user_id}/{language}")
async def get_question(user_id: str, language: str, topic: str = None):
    try:
        recall_res = requests.post(
            f"{HINDSIGHT_BASE}/banks/{BANK_ID}/recall",
            json={"query": f"What has user {user_id} struggled with?"},
            headers=hs_headers()
        )
        results = recall_res.json().get("results", [])
        weak_spots = "\n".join([r.get("text", "") for r in results]) or "No history yet."

        if topic:
            prompt = f"""
Generate a single {language} coding question specifically about {topic}.
Return ONLY the question, nothing else.
"""
        else:
            prompt = f"""
Generate a single {language} coding question for a student.
Their past weak spots are: {weak_spots}
If they have weak spots, target those topics.
If no history, give a beginner friendly question.
Return ONLY the question, nothing else.
"""
        chat = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        question = chat.choices[0].message.content
        return {"question": question}

    except Exception as e:
        return {"error": str(e)}


# --- TEST ---
@app.get("/")
def root():
    return {"status": "CodeSensei backend is running 🔥"}


