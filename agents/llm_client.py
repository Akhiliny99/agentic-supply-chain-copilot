
import os
import random

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()


def complete(system_prompt: str, user_prompt: str) -> str:
    if LLM_PROVIDER == "groq":
        from groq import Groq  
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content

    if LLM_PROVIDER == "vertex":
        from vertexai.generative_models import GenerativeModel  
        model = GenerativeModel("gemini-2.5-pro")
        resp = model.generate_content(f"{system_prompt}\n\n{user_prompt}")
        return resp.text

 
    return _mock_reasoning(system_prompt, user_prompt)


def _mock_reasoning(system_prompt: str, user_prompt: str) -> str:
    """Not a real LLM call — a readable, deterministic explanation string so
    the audit trail and dashboard have something meaningful to show without
    needing an API key. Swap LLM_PROVIDER to use a real model."""
    random.seed(hash(user_prompt) % (2**32))
    confidence = round(random.uniform(0.45, 0.95), 2)
    return (
        f"[mock-llm] Reasoned over provided context. "
        f"Confidence={confidence}. See structured output for the decision."
    )
