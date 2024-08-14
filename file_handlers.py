import tempfile
from io import BytesIO
from PIL import Image
import pandas as pd
import fitz  # PyMuPDF
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import docx
import streamlit as st
from openai_client import OpenAIClient

def encode_image(image):
    """Encodes a PIL Image object to a Base64 string."""
    with BytesIO() as buffer:
        image.save(buffer, format=image.format)
        return base64.b64encode(buffer.getvalue()).decode()

def process_images_concurrently(images, openai_client, context):
    """Transcribes images to text using OpenAI API, processing them concurrently."""
    image_texts = []
    error_messages = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for image in images:
            try:
                img = Image.open(image)  # Open the image from BytesIO
                base64_image = encode_image(img)  # Encode the image
                futures[executor.submit(openai_client.transcribe_image, base64_image)] = image
            except Exception as e:
                error_messages.append(f"Error opening image for {context}: {e}")

        for i, future in enumerate(as_completed(futures)):
            try:
                image_text = future.result()
                image_texts.append(f"Image {i+1}: {image_text}")
            except Exception as e:
                error_messages.append(f"Error processing an image from {context}: {e}")

    if error_messages:
        for error in error_messages:
            st.error(error)  # Display errors on the main thread

    return image_texts

def extract_images_from_docx(doc):
    """Extracts images from a DOCX document."""
    images = []
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            try:
                image = rel.target_part.blob
                if image:
                    image_stream = BytesIO(image)
                    images.append(image_stream)
            except Exception as e:
                st.warning(f"Could not extract image from DOCX: {e}")
    return images

def extract_images_from_pptx(slide):
    """Extracts images from a PPTX slide."""
    images = []
    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            try:
                if hasattr(shape, 'image') and shape.image.blob:
                    image_stream = BytesIO(shape.image.blob)
                    images.append(image_stream)
                else:
                    st.warning(f"Slide contains a shape marked as an image but lacks an embedded image.")
            except Exception as e:
                st.error(f"Error processing an image on slide: {e}")
    return images

def extract_images_from_pdf(page):
    """Extracts images from a PDF page."""
    images = []
    image_list = page.get_images(full=True)
    for img in image_list:
        try:
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            if image_bytes:
                image_stream = BytesIO(image_bytes)
                images.append(image_stream)
        except Exception as e:
            st.warning(f"Could not extract image from PDF: {e}")
    return images

def read_docx(file, openai_client):
    """Reads DOCX files, extracts text and transcribes images."""
    doc = docx.Document(file)
    content = []
    for para in doc.paragraphs:
        content.append(para.text + "\n")  # Add line breaks after each paragraph

    images = extract_images_from_docx(doc)
    if images:
        image_texts = process_images_concurrently(images, openai_client, "DOCX")
        content.append("\nImage Descriptions:\n" + "\n".join(image_texts) + "\n")

    return "".join(content)

def read_txt(file):
    return file.read().decode("utf-8")

def read_excel(file):
    df = pd.read_excel(file)
    return df.to_string(index=False)

def read_pdf(file, openai_client):
    """Reads PDF files, extracts text and transcribes images."""
    document = fitz.open(stream=file.read(), filetype="pdf")
    pages = []

    for page_num in range(len(document)):
        page = document.load_page(page_num)
        page_content = f"--- Page {page_num + 1} ---\n"
        page_content += page.get_text("text") + "\n"  # Ensure proper text extraction with line breaks

        images = extract_images_from_pdf(page)
        if images:
            image_texts = process_images_concurrently(images, openai_client, f"Page {page_num + 1}")
            page_content += "\nImage Descriptions:\n" + "\n".join(image_texts) + "\n"

        pages.append(page_content)

    return "\n".join(pages)

def read_pptx(file, openai_client):
    """Reads PPTX files, extracts text and transcribes images."""
    presentation = Presentation(file)
    slides = []

    for slide_num, slide in enumerate(presentation.slides, start=1):
        slide_content = f"--- Slide {slide_num} ---\n"
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    slide_content += paragraph.text + "\n"  # Add line breaks after each paragraph

        images = extract_images_from_pptx(slide)
        if images:
            image_texts = process_images_concurrently(images, openai_client, f"Slide {slide_num}")
            slide_content += "\nImage Descriptions:\n" + "\n".join(image_texts) + "\n"

        slides.append(slide_content)

    return "\n".join(slides)

def save_as_docx(minutes):
    """Save meeting minutes or any text content into a Word document."""
    doc = docx.Document()
    for key, value in minutes.items():
        heading = ' '.join(word.capitalize() for word in key.split('_'))
        doc.add_heading(heading, level=1)
        doc.add_paragraph(value)
        doc.add_paragraph()
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

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

    return "\n\n".join(transcriptions)
