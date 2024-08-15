import streamlit as st
import os
from openai import OpenAI
from docx import Document
from io import BytesIO
import moviepy.editor as mp
import tempfile
import pandas as pd
import fitz
import base64
import requests
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_quill import st_quill
from pptx import Presentation
from PIL import Image

api_key = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=api_key)

# Functions

def transcribe_audio(audio_file):
    transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
    return transcription['text'] if isinstance(transcription, dict) else transcription.text

def generate_response(transcription, model, custom_prompt):
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": custom_prompt},
            {"role": "user", "content": transcription}
        ]
    )
    return response.choices[0].message.content

def save_as_docx(minutes):
    doc = Document()
    for key, value in minutes.items():
        heading = ' '.join(word.capitalize() for word in key.split('_'))
        doc.add_heading(heading, level=1)
        doc.add_paragraph(value)
        doc.add_paragraph()
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def convert_video_to_mp3(uploaded_file, suffix):
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_video_file:
        temp_video_file.write(uploaded_file.getbuffer())
    video = mp.VideoFileClip(temp_video_file.name)

    if not video.audio:
        st.error(f"The uploaded {suffix} file does not contain an audio track.")
        return None

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as audio_file:
        video.audio.write_audiofile(audio_file.name)
    return audio_file.name

def read_file(file, file_type):
    if file_type == "docx":
        return "\n".join([para.text for para in docx.Document(file).paragraphs])
    elif file_type == "txt":
        return file.read().decode("utf-8")
    elif file_type == "xlsx":
        return pd.read_excel(file).to_string(index=False)
    elif file_type == "pdf":
        return "".join([page.get_text() for page in fitz.open(stream=file.read(), filetype="pdf")])
    elif file_type == "pptx":
        presentation = Presentation(file)
        return "\n".join([shape.text for slide in presentation.slides for shape in slide.shapes if hasattr(shape, "text")])

def encode_image(image):
    with BytesIO() as buffer:
        image.save(buffer, format=image.format)
        return base64.b64encode(buffer.getvalue()).decode()

def transcribe_image(image_file):
    image = Image.open(image_file)
    base64_image = encode_image(image)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o-mini",  
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What’s in this image?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ],
        "max_tokens": 300
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    return response.json()['choices'][0]['message']['content']

# Pre-canned prompts and their respective headings
pre_canned_prompts = {
    "meeting_summary": {
        "summary": {
            "prompt": "You are a highly skilled AI trained in language comprehension and summarization. I would like you to read the following text and summarize it into a concise abstract paragraph. Aim to retain the most important points, providing a coherent and readable summary that could help a person understand the main points of the discussion without needing to read the entire text. Please avoid unnecessary details or tangential points.",
            "heading": "Summary"
        },
        "key_points": {
            "prompt": "You are a proficient AI with a specialty in distilling information into key points. Based on the following text, identify and list the main points that were discussed or brought up. These should be the most important ideas, findings, or topics that are crucial to the essence of the discussion. Your goal is to provide a list that someone could read to quickly understand what was talked about.",
            "heading": "Key Points"
        },
        "action_items": {
            "prompt": "You are an AI expert in analyzing conversations and extracting action items. Please review the text and identify any tasks, assignments, or actions that were agreed upon or mentioned as needing to be done. These could be tasks assigned to specific individuals, or general actions that the group has decided to take. Please list these action items clearly and concisely.",
            "heading": "Action Items"
        },
        "sentiment": {
            "prompt": "As an AI with expertise in language and emotion analysis, your task is to analyze the sentiment of the following text. Please consider the overall tone of the discussion, the emotion conveyed by the language used, and the context in which words and phrases are used. Indicate whether the sentiment is generally positive, negative, or neutral, and provide brief explanations for your analysis where possible.",
            "heading": "Sentiment Analysis"
        }
    },
    "user_research": {
        "summary": {
            "prompt": "You are a highly skilled AI trained in language comprehension and summarization. I would like you to read the following text and summarize it into a concise abstract paragraph. Aim to retain the most important points, providing a coherent and readable summary that could help a person understand the main points of the discussion without needing to read the entire text. Please avoid unnecessary details or tangential points.",
            "heading": "Summary"
        },
        "biographical_info": {
            "prompt": "You are a proficient AI with a specialty in distilling biographical information about people. Based on the following text, please identify biographical information about the subject of the research study.",
            "heading": "Biographical Info"
        },
        "key_insights": {
            "prompt": "You are a proficient AI with a specialty in distilling information into key points. Based on the following user research transcript, please identify the key insights. Identify and list the main points that were discussed or brought up. These should be the most important ideas, findings, or topics that are crucial to the essence of the discussion. Your goal is to provide a list that someone could read to quickly understand what was talked about.",
            "heading": "Key Insights"
        },
        "recommendations": {
            "prompt": "You are a proficient AI with a specialty in identifying meaningful product opportunities. Based on the transcript, please identify product recommendations/opportunities.",
            "heading": "Recommendations"
        }
    },
    "action_items": {
        "action_items": {
            "prompt": "You are an AI expert in analyzing conversations and extracting action items. Please review the text and identify any tasks, assignments, or actions that were agreed upon or mentioned as needing to be done. These could be tasks assigned to specific individuals, or general actions that the group has decided to take. Please list these action items clearly and concisely. Each task should be formatted as follows: Topic. Description of the task. Do not use sub-bullets.",
            "heading": "Action Items"
        }
    }
}

def process_uploaded_files(uploaded_files):
    transcriptions = []
    for uploaded_file in uploaded_files:
        file_type = uploaded_file.type.split('/')[-1]

        if file_type in ["quicktime", "mp4"]:
            suffix = f".{file_type}"
            audio_file_path = convert_video_to_mp3(uploaded_file, suffix)
            if audio_file_path:
                with open(audio_file_path, "rb") as f:
                    transcriptions.append(transcribe_audio(f))
        elif file_type == "mpeg":
            transcriptions.append(transcribe_audio(uploaded_file))
        elif file_type in ["docx", "txt", "xlsx", "pdf", "pptx"]:
            transcriptions.append(read_file(uploaded_file, file_type))
        elif file_type in ["jpeg", "png"]:
            transcriptions.append(transcribe_image(uploaded_file))

    return "\n\n".join(transcriptions) if transcriptions else None

def main():
    st.markdown(
        """
        <style>
        .reportview-container .main .block-container { padding-left: 0rem; padding-right: 0rem; max-width: 100%; margin: 0 auto; }
        .css-18e3th9 { flex: 1 1 100%; width: 100%; padding: 2rem 1rem 1rem; }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.sidebar.title("Wonk")
    st.sidebar.info("Upload mp3, mp4, mov, docx, txt, xlsx, pdf, pptx, or image files to start!")
    uploaded_files = st.sidebar.file_uploader("Upload audio, video, text, or image files", type=["mp3", "mp4", "mov", "docx", "txt", "xlsx", "pdf", "pptx", "jpg", "jpeg", "png"], accept_multiple_files=True)
    process_files = st.sidebar.button("Process Files")

    if uploaded_files and process_files:
        transcription = process_uploaded_files(uploaded_files)
        if transcription:
            st.session_state.transcription = transcription

    if "transcription" in st.session_state:
        transcription = st.session_state.transcription
        with st.expander("Transcription", expanded=True):
            st.subheader("Transcription")
            st.session_state.transcription = st_quill(value=transcription, key='transcription_editor')

        st.sidebar.info("Select what you'd like to create!")
        summary_type = st.sidebar.radio("Select the type of summary you want to generate:", ("", "Meeting Summary", "User Research Synthesis", "Action Items"), index=0)

        if summary_type:
            prompts = pre_canned_prompts.get(summary_type.lower().replace(" ", "_"), {})
            selected_prompts = {key: st.sidebar.checkbox(value["heading"]) for key, value in prompts.items() if st.sidebar.checkbox(value["heading"])}

            if selected_prompts and st.sidebar.button("Create GPT Tasks"):
                st.session_state.prompts = [{"prompt": prompts[key]["prompt"], "model": "gpt-4o", "heading": prompts[key]["heading"]} for key in selected_prompts]

        if st.session_state.get('prompts'):
            st.info("Click generate to create your document!")
            if st.button("Generate"):
                minutes = {info["heading"]: generate_response(st.session_state.transcription, info["model"], info["prompt"]) for info in st.session_state.prompts}
                st.session_state.generated_minutes = minutes

        if st.session_state.get('generated_minutes'):
            with st.expander("Generated Minutes", expanded=True):
                for key, value in st.session_state.generated_minutes.items():
                    st.write(f"**{key}**")
                    st.write(value)

                docx_file = save_as_docx(st.session_state.generated_minutes)
                st.download_button("Download Meeting Minutes", data=docx_file, file_name="meeting_minutes.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

            if "Action Items" in st.session_state.generated_minutes:
                with st.expander("Action Items", expanded=True):
                    st.subheader("Action Items")
                    action_items = st.session_state.generated_minutes["Action Items"]
                    action_items_list = [item.strip() for item in action_items.split('\n') if item]

                    grid_data = [{"Task Number": idx, "Task": task, "Draft Email": False, "Draft Slack": False, "Draft Memo": False} for idx, task in enumerate(action_items_list, 1)]
                    grid_options = GridOptionsBuilder.from_dataframe(pd.DataFrame(grid_data)).build()
                    grid_response = AgGrid(pd.DataFrame(grid_data), gridOptions=grid_options, height=300, fit_columns_on_grid_load=True, update_mode=GridUpdateMode.MODEL_CHANGED)

                    for index, row in grid_response['data'].iterrows():
                        for task_type in ["Email", "Slack", "Memo"]:
                            if row[f"Draft {task_type}"]:
                                prompt_key = f"{task_type.lower()}_prompt_{row['Task Number']}"
                                st.session_state[prompt_key] = f"Draft a {task_type.lower()} for the following action item: {row['Task']}"
                                row[f"Draft {task_type}"] = False
                                st.subheader(f"{task_type} Draft for Task {row['Task Number']}")
                                st.write(st.session_state[prompt_key])
                                if st.button(f"Generate {task_type} for Task {row['Task Number']}"):
                                    draft = generate_response(st.session_state.transcription, "gpt-4o", st.session_state[prompt_key])
                                    st.write(draft)

if __name__ == "__main__":
    main()
