import os
import json
from google import genai

# Initialize Gemini client
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

def handler(request):
    try:
        # Parse incoming JSON
        body = request.get_json()
        prompt = body.get("message", "")

        if not prompt:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "No message provided"})
            }

        # Generate response
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "reply": response.text
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }
