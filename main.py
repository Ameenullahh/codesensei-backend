from dotenv import load_dotenv
load_dotenv()
import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

# --- API KEYS ---
GROQ_KEY = os.environ.get("GROQ_KEY")
HINDSIGHT_KEY = os.environ.get("HINDSIGHT_KEY")
HINDSIGHT_BASE = os.environ.get("HINDSIGHT_BASE")
BANK_ID = os.environ.get("BANK_ID")

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
    question: str = ""

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
        past_mistakes = "\n".join([m.get("text", "") for m in results]) or "No past mistakes yet."

        # 2. build prompt
        prompt = f"""
You are {req.mentor}. Stay completely in character the entire time.
This student previously struggled with: {past_mistakes}

The question they were supposed to solve was:
{req.question}

Now review their {req.language} code:
{req.code}

First check if their code actually solves the given question. If they solved a completely different problem, call that out in character and tell them to solve the actual question.
If the code is wrong: roast them in your character's voice, explain the mistake, give a hint.
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

        # 5. get next question automatically
        weak_spots = "\n".join([m.get("text", "") for m in results]) or "No history yet."
        next_prompt = f"""
Generate a single {req.language} coding question for a student.
Their past weak spots are: {weak_spots}
If they have weak spots, target those topics.
If no history, give a beginner friendly question.
Return ONLY the question, nothing else.
"""
        next_chat = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": next_prompt}],
            model="llama-3.3-70b-versatile"
        )
        next_question = next_chat.choices[0].message.content

        return {"feedback": feedback, "mentor": req.mentor, "next_question": next_question}

    except Exception as e:
        print(f"ERROR: {e}")
        return {"error": str(e)}

# --- QUESTION ENDPOINT ---
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
# --- CHAT ENDPOINT ---
class ChatRequest(BaseModel):
    message: str
    mentor: str
    user_id: str
    language: str
    conversation_history: list = []

@app.post("/chat")
async def chat_with_mentor(req: ChatRequest):
    try:
        # build conversation messages
        messages = [
            {
                "role": "system",
                "content": f"""You are {req.mentor}. Stay completely in character the entire time.
You are a coding mentor helping a student learn programming.
You can explain concepts, answer questions, give hints, and have real conversations.
Be helpful but stay in character — use their personality, their way of speaking, their humor.
Keep responses conversational and under 5 sentences."""
            }
        ]

        # add conversation history so it remembers what was said
        for msg in req.conversation_history:
            messages.append(msg)

        # add the new message
        messages.append({"role": "user", "content": req.message})

        # get groq response
        chat = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile"
        )
        response = chat.choices[0].message.content

        return {"response": response, "mentor": req.mentor}

    except Exception as e:
        print(f"ERROR: {e}")
        return {"error": str(e)}

# --- DIFFICULTY ENDPOINT ---
class DifficultyRequest(BaseModel):
    message: str
    user_id: str
    language: str
    current_question: str

@app.post("/difficulty")
async def adjust_difficulty(req: DifficultyRequest):
    try:
        # detect what user wants
        prompt = f"""
The user said: "{req.message}"
Their current question was: "{req.current_question}"

Detect if they want:
- harder question
- easier question
- different topic

Then generate a new {req.language} coding question accordingly.
Return ONLY the new question, nothing else.
"""
        chat = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        new_question = chat.choices[0].message.content
        return {"question": new_question}

    except Exception as e:
        return {"error": str(e)}
# --- TEST ---
@app.get("/")
def root():
    return {"status": "CodeSensei backend is running"}
