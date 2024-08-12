import tempfile
import moviepy.editor as mp
import docx
import pandas as pd
import fitz
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from PIL import Image
from io import BytesIO
import base64
import os
import requests
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import time

def convert_video_to_mp3(uploaded_file, suffix):
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_video_file:
        temp_video_file.write(uploaded_file.getbuffer())
        temp_video_file_path = temp_video_file.name

    video = mp.VideoFileClip(temp_video_file_path)

    if video.audio is None:
        return None

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as audio_file:
        audio_file_path = audio_file.name

    video.audio.write_audiofile(audio_file_path)
    return audio_file_path

def read_docx(file, openai_client):
    doc = docx.Document(file)
    text = "\n".join([para.text for para in doc.paragraphs])
    images = []

    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            image = rel.target_part.blob
            image_stream = BytesIO(image)
            images.append(image_stream)

    image_texts = process_images_concurrently(images, openai_client, "DOCX")
    return text + "\n" + "\n".join(image_texts)

def read_txt(file):
    return file.read().decode("utf-8")

def read_excel(file):
    df = pd.read_excel(file)
    return df.to_string(index=False)

def read_pdf(file, openai_client):
    document = fitz.open(stream=file.read(), filetype="pdf")
    text = ""
    images = []

    for page_num in range(len(document)):
        page = document.load_page(page_num)
        text += page.get_text()
        image_list = page.get_images(full=True)
        for image_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = document.extract_image(xref)
            image_bytes = base_image["image"]
            image_stream = BytesIO(image_bytes)
            images.append(image_stream)

    image_texts = process_images_concurrently(images, openai_client, "PDF")
    return text + "\n" + "\n".join(image_texts)

def read_pptx(file, openai_client):
    presentation = Presentation(file)
    slides = []

    for slide_num, slide in enumerate(presentation.slides, start=1):
        slide_text = f"--- Slide {slide_num} ---\n"
        images = []
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                slide_text += shape.text + "\n"
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                image = shape.image
                image_stream = BytesIO(image.blob)
                images.append(image_stream)

        slide_text += "\n".join(process_images_concurrently(images, openai_client, f"Slide {slide_num}"))
        slides.append(slide_text)

    return "\n".join(slides)

def process_images_concurrently(images, openai_client, context):
    image_texts = []
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(transcribe_image, openai_client, image_stream): image_stream for image_stream in images}
        for i, future in enumerate(as_completed(futures)):
            try:
                image_text = future.result()
                st.info(f"Processed image {i+1}/{len(images)} from {context}")
                image_texts.append(image_text)
            except Exception as e:
                st.error(f"Error processing image {i+1}/{len(images)} from {context}: {e}")
    return image_texts

def encode_image(image):
    with BytesIO() as buffer:
        image.save(buffer, format=image.format)
        return base64.b64encode(buffer.getvalue()).decode()

def transcribe_image(openai_client, image_stream):
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    image = Image.open(image_stream)
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
                    {
                        "type": "text",
                        "text": "What’s in this image?"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    ]
                ]
            }
        ],
        "max_tokens": 300
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    if response.status_code != 200:
        st.error(f"Error: {response.status_code} - {response.text}")
        response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

def trim_silence(audio_file, file_name):
    sound = AudioSegment.from_file(audio_file, format="mp3")
    nonsilent_ranges = detect_nonsilent(sound, min_silence_len=1000, silence_thresh=sound.dBFS-16)
    if nonsilent_ranges:
        start_trim, end_trim = nonsilent_ranges[0]
        trimmed_sound = sound[start_trim:]
        trimmed_audio_file = BytesIO()
        trimmed_sound.export(trimmed_audio_file, format="mp3")
        trimmed_audio_file.name = file_name  # Set the name attribute for the BytesIO object
        trimmed_audio_file.seek(0)
        return trimmed_audio_file
    return audio_file

def process_files_concurrently(uploaded_files, openai_client):
    transcriptions = []
    with ThreadPoolExecutor() as executor:
        futures = []
        for i, uploaded_file in enumerate(uploaded_files):
            st.info(f"Submitting file {i+1}/{len(uploaded_files)}: {getattr(uploaded_file, 'name', 'unknown')} for processing")
            if uploaded_file.type in ["video/quicktime", "video/mp4"]:
                suffix = ".mov" if uploaded_file.type == "video/quicktime" else ".mp4"
                futures.append(executor.submit(convert_video_to_mp3, uploaded_file, suffix))
            elif uploaded_file.type == "audio/mpeg":
                trimmed_audio_file = trim_silence(uploaded_file, uploaded_file.name)
                futures.append(executor.submit(openai_client.transcribe_audio, trimmed_audio_file))
            elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                futures.append(executor.submit(read_docx, uploaded_file, openai_client))
            elif uploaded_file.type == "text/plain":
                futures.append(executor.submit(read_txt, uploaded_file))
            elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                futures.append(executor.submit(read_excel, uploaded_file))
            elif uploaded_file.type == "application/pdf":
                futures.append(executor.submit(read_pdf, uploaded_file, openai_client))
            elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
                futures.append(executor.submit(read_pptx, uploaded_file, openai_client))
            elif uploaded_file.type in ["image/jpeg", "image/png"]:
                base64_image = encode_image(Image.open(uploaded_file))
                futures.append(executor.submit(openai_client.transcribe_image, base64_image))

        for i, future in enumerate(as_completed(futures)):
            try:
                result = future.result()
                if isinstance(result, str):
                    transcriptions.append(result)
                elif isinstance(result, list):
                    transcriptions.extend(result)
                st.info(f"Completed processing file {i+1}/{len(uploaded_files)}")
            except Exception as e:
                st.error(f"Error processing file {i+1}/{len(uploaded_files)}: {e}")

    return transcriptions
