import os
import requests
from openai import OpenAI
import streamlit as st
import time

class OpenAIClient:
    def __init__(self):
        self.api_key = st.secrets["openai"]["api_key"]
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in Streamlit secrets")
        self.client = OpenAI(api_key=self.api_key)

    def transcribe_audio(self, audio_file):
        # Add a short delay before transcription
        time.sleep(1)
        response = self.client.Audio.transcriptions.create(model="whisper-1", file=audio_file)
        return response['text'] if isinstance(response, dict) else response.text

    def generate_response(self, transcription, model, custom_prompt):
        response = self.client.Chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": custom_prompt},
                {"role": "user", "content": transcription}
            ]
        )
        return response['choices'][0]['message']['content'] if 'choices' in response else response.choices[0].message.content

    def transcribe_image(self, base64_image):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What’s in this image?"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        if response.status_code != 200:
            raise Exception(f"Error: {response.status_code} - {response.text}")
        return response.json()['choices'][0]['message']['content']
