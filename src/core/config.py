"""
Lab 11 — Configuration & API Key Setup
"""
import os


def setup_api_key():
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        env_path = Path(__file__).resolve().parents[2] / ".env"
        load_dotenv(env_path, encoding="utf-8")
    except Exception:
        pass

    if "GOOGLE_API_KEY" in os.environ and "GEMINI_API_KEY" not in os.environ:
        os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]
        
    if not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = "dummy_key_for_groq_fallback"
        os.environ["GOOGLE_API_KEY"] = "dummy_key_for_groq_fallback"
            
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "0"
    print("API key loaded (Groq fallback enabled).")
    _patch_gemini_with_groq_fallback()


def _patch_gemini_with_groq_fallback():
    try:
        from google.adk.models.google_llm import Gemini
        from google.adk.models.llm_response import LlmResponse
        from google.genai import types
        import urllib.request
        import json
        import asyncio

        original_generate = Gemini.generate_content_async

        async def patched_generate(self, llm_request, stream=False):
            try:
                async for resp in original_generate(self, llm_request, stream=stream):
                    yield resp
            except Exception as e:
                groq_key = os.environ.get("GROQ_API_KEY")
                if not groq_key:
                    raise e
                
                messages = []
                sys_inst = getattr(llm_request.config, "system_instruction", None)
                if sys_inst:
                    if isinstance(sys_inst, str):
                        sys_text = sys_inst
                    else:
                        sys_text = "".join(p.text for p in getattr(sys_inst, "parts", []) if hasattr(p, "text"))
                    if sys_text:
                        messages.append({"role": "system", "content": sys_text})

                for content in llm_request.contents:
                    role = "assistant" if content.role in ("model", "assistant") else "user"
                    parts_text = "".join(p.text for p in content.parts if hasattr(p, "text") and p.text)
                    if parts_text:
                        messages.append({"role": role, "content": parts_text})

                req_payload = {
                    "model": "llama-3.1-8b-instant",
                    "messages": messages,
                }
                
                def _call_groq():
                    req = urllib.request.Request(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {groq_key}",
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0",
                        },
                        data=json.dumps(req_payload).encode("utf-8"),
                    )
                    with urllib.request.urlopen(req) as response:
                        res_data = json.loads(response.read().decode("utf-8"))
                        return res_data["choices"][0]["message"]["content"]

                try:
                    reply = await asyncio.to_thread(_call_groq)
                    gen_resp = types.GenerateContentResponse(
                        candidates=[
                            types.Candidate(
                                content=types.Content(
                                    role="model",
                                    parts=[types.Part.from_text(text=reply)]
                                )
                            )
                        ]
                    )
                    yield LlmResponse.create(gen_resp)
                except Exception as inner_e:
                    raise e

        Gemini.generate_content_async = patched_generate
        print("Groq API fallback active.")
    except Exception:
        pass


# Allowed banking topics (used by topic_filter)
ALLOWED_TOPICS = [
    "banking", "account", "transaction", "transfer",
    "loan", "interest", "savings", "credit",
    "deposit", "withdrawal", "balance", "payment",
    "tai khoan", "giao dich", "tiet kiem", "lai suat",
    "chuyen tien", "the tin dung", "so du", "vay",
    "ngan hang", "atm",
]

# Blocked topics (immediate reject)
BLOCKED_TOPICS = [
    "hack", "exploit", "weapon", "drug", "illegal",
    "violence", "gambling", "bomb", "kill", "steal",
]
