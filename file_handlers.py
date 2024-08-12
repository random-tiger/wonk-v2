import tempfile
import moviepy.editor as mp
from io import BytesIO
from PIL import Image
import base64
import os
import requests
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import time

def convert_video_to_mp3(uploaded_file, suffix):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_video_file:
            temp_video_file.write(uploaded_file.getbuffer())
            temp_video_file_path = temp_video_file.name

        video = mp.VideoFileClip(temp_video_file_path)

        if video.audio is None:
            st.error("No audio track found in the video file.")
            return None

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as audio_file:
            audio_file_path = audio_file.name

        # Using ffmpeg directly for conversion to avoid potential issues
        video.audio.write_audiofile(audio_file_path, codec='mp3')

        return audio_file_path
    except Exception as e:
        st.error(f"Error converting video to audio: {e}")
        return None

# Other existing functions remain unchanged

def trim_silence(audio_file, file_name, silence_len=1000, silence_thresh=-40):
    sound = AudioSegment.from_file(audio_file, format="mp3")
    nonsilent_ranges = detect_nonsilent(sound, min_silence_len=silence_len, silence_thresh=silence_thresh)
    
    if nonsilent_ranges:
        start_trim = nonsilent_ranges[0][0]
        end_trim = nonsilent_ranges[-1][1]
        trimmed_sound = sound[start_trim:end_trim]
        
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
                audio_file_path = convert_video_to_mp3(uploaded_file, suffix)
                if audio_file_path:
                    trimmed_audio_file = trim_silence(audio_file_path, uploaded_file.name)
                    futures.append(executor.submit(openai_client.transcribe_audio, trimmed_audio_file))
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
                transcriptions.append(result)
                st.info(f"Completed processing file {i+1}/{len(uploaded_files)}")
            except Exception as e:
                st.error(f"Error processing file {i+1}/{len(uploaded_files)}: {e}")

    return transcriptions
