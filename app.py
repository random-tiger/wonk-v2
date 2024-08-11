import streamlit as st
import tempfile
from file_handlers import (
    convert_video_to_mp3,
    read_docx,
    read_txt,
    read_excel,
    read_pdf,
    read_pptx,
    encode_image,
    process_files_concurrently,
    trim_silence
)
from openai_client import OpenAIClient
from pre_canned_prompts import pre_canned_prompts
from io import BytesIO
from PIL import Image
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_quill import st_quill
import pandas as pd
from docx import Document
import time

# Initialize OpenAI client
try:
    openai_client = OpenAIClient()
except ValueError as e:
    st.error(f"Error initializing OpenAI client: {e}")
    st.stop()

# Function to save meeting minutes as a Word document
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

def process_files(uploaded_files, openai_client):
    with st.spinner("Processing files..."):
        return process_files_concurrently(uploaded_files, openai_client)

def main():
    st.markdown(
        """
        <style>
        .reportview-container .main .block-container {
            padding-left: 0rem;
            padding-right: 0rem;
            max-width: 100%;
            margin: 0 auto;
        }
        .css-18e3th9 {
            flex: 1 1 100%;
            width: 100%;
            padding: 2rem 1rem 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.sidebar.title("Wonk")
    st.sidebar.info("Upload mp3, mp4, mov, docx, txt, xlsx, pdf, pptx, or image files to start!")
    uploaded_files = st.sidebar.file_uploader("Upload audio, video, text, or image files", type=["mp3", "mp4", "mov", "docx", "txt", "xlsx", "pdf", "pptx", "jpg", "jpeg", "png"], accept_multiple_files=True)
    process_files_button = st.sidebar.button("Process Files")

    if uploaded_files is not None and process_files_button:
        if "transcriptions" not in st.session_state:
            st.session_state.transcriptions = []

        transcriptions = process_files(uploaded_files, openai_client)
        st.session_state.transcriptions.extend(transcriptions)

        if st.session_state.transcriptions:
            combined_transcription = "\n\n".join(st.session_state.transcriptions)
            st.session_state.transcription = combined_transcription

    if "transcription" not in st.session_state:
        st.session_state.transcription = ""

    if "editor_content" not in st.session_state:
        st.session_state.editor_content = ""

    transcription = st.session_state.transcription
    editor_content = st.session_state.editor_content

    if transcription:
        with st.expander("Transcription", expanded=True):
            st.subheader("Transcription")

            if editor_content != transcription:
                editor_content = transcription
                st.session_state.editor_content = editor_content

            editor_content = st_quill(value=editor_content, key='transcription_editor')

            if editor_content != st.session_state.editor_content:
                st.session_state.editor_content = editor_content

        st.sidebar.info("Select what you'd like to create!")
        
        # Clear the prompts if a new summary type is selected
        if 'selected_summary_type' not in st.session_state:
            st.session_state.selected_summary_type = ""
        
        summary_type = st.sidebar.radio(
            "Select the type of summary you want to generate:",
            ("", "Meeting Summary", "User Research Synthesis", "Action Items", "Retro", "Document Review"),
            index=0
        )
        
        if summary_type != st.session_state.selected_summary_type:
            st.session_state.selected_summary_type = summary_type
            st.session_state.prompts = []

        if 'prompts' not in st.session_state:
            st.session_state.prompts = []

        checkboxes = {}
        if summary_type == "Meeting Summary":
            st.sidebar.markdown("### Meeting Summary Prompts")
            st.sidebar.info("Select the sections you'd like in your document!")
            checkboxes = {
                "summary": st.sidebar.checkbox("Summary"),
                "key_points": st.sidebar.checkbox("Key Points"),
                "action_items": st.sidebar.checkbox("Action Items"),
                "sentiment": st.sidebar.checkbox("Sentiment Analysis")
            }

        elif summary_type == "User Research Synthesis":
            st.sidebar.markdown("### User Research Synthesis Prompts")
            st.sidebar.info("Select the sections you'd like in your document!")
            checkboxes = {
                "summary": st.sidebar.checkbox("Summary", key="user_summary"),
                "biographical_info": st.sidebar.checkbox("Biographical Info"),
                "key_insights": st.sidebar.checkbox("Key Insights"),
                "recommendations": st.sidebar.checkbox("Recommendations")
            }

        elif summary_type == "Action Items":
            st.sidebar.markdown("### Action Items Prompt")
            st.sidebar.info("Select the section to generate action items!")
            checkboxes = {
                "action_items": st.sidebar.checkbox("Action Items", key="action_items")
            }

        elif summary_type == "Retro":
            st.sidebar.markdown("### Retro Prompts")
            st.sidebar.info("Select the sections you'd like in your document!")
            checkboxes = {
                "tl;dr": st.sidebar.checkbox("tl;dr"),
                "background": st.sidebar.checkbox("Background"),
                "what_was_supposed_to_happen": st.sidebar.checkbox("What Was Supposed to Happen"),
                "what_happened": st.sidebar.checkbox("What Happened"),
                "what_went_well": st.sidebar.checkbox("What Went Well"),
                "what_could_be_improved": st.sidebar.checkbox("What Could Be Improved"),
                "next_steps_action_plan": st.sidebar.checkbox("Next Steps / Action Plan")
            }

        elif summary_type == "Document Review":
            st.sidebar.markdown("### Document Review Prompts")
            st.sidebar.info("Select the sections you'd like in your document!")
            checkboxes = {
                "comments": st.sidebar.checkbox("Comments"),
                "simplified_summary": st.sidebar.checkbox("Simplified Summary")
            }

        if any(checkboxes.values()):
            st.sidebar.info("Click 'Create GPT Tasks' to proceed")
            if st.sidebar.button("Create GPT Tasks"):
                for key, checked in checkboxes.items():
                    if checked:
                        try:
                            st.session_state.prompts.append({
                                "prompt": pre_canned_prompts[summary_type.lower().replace(" ", "_")][key]["prompt"],
                                "model": "gpt-4o",
                                "heading": pre_canned_prompts[summary_type.lower().replace(" ", "_")][key]["heading"]
                            })
                        except KeyError as e:
                            st.error(f"KeyError: {e} - summary_type: {summary_type.lower().replace(' ', '_')}, key: {key}")
                            st.stop()

        for i, prompt_info in enumerate(st.session_state.prompts):
            with st.expander(f"GPT Task {i+1} - {prompt_info['heading']}", expanded=True):
                st.info("Update the pre-canned prompt to customize!")
                prompt_info["model"] = st.text_input("Model", value=prompt_info["model"], key=f"model_{i}")
                prompt_info["prompt"] = st.text_area("Prompt", value=prompt_info["prompt"], key=f"prompt_{i}")
                if st.button("Remove GPT Task", key=f"remove_gpt_task_{i}"):
                    st.session_state.prompts.pop(i)
                    break

        if st.session_state.prompts:
            st.info("Click generate to create your document!")
            st.markdown(
                """
                <style>
                .blue-button button {
                    background-color: #007BFF !important;
                    color: white !important;
                }
                </style>
                """,
                unsafe_allow_html=True
            )
            if st.button("Generate", key="generate"):
                minutes = {}
                for i, prompt_info in enumerate(st.session_state.prompts):
                    task_key = prompt_info["heading"] if prompt_info["heading"] else f"Task {i+1}"
                    minutes[task_key] = openai_client.generate_response(st.session_state.transcription, prompt_info["model"], prompt_info["prompt"])
                st.session_state.generated_minutes = minutes

        if 'generated_minutes' in st.session_state:
            with st.expander("Generated Minutes", expanded=True):
                for key, value in st.session_state.generated_minutes.items():
                    st.write(f"**{key}**")
                    st.write(value)

                st.subheader("Final Edit")
                final_text = "\n\n".join(f"**{key}**\n\n{value}" for key, value in st.session_state.generated_minutes.items())
                edited_final_text = st_quill(value=final_text, key='final_editor')
                st.session_state.final_text = edited_final_text

                docx_file = save_as_docx(st.session_state.generated_minutes)

                st.info("Click download to get a docx file of your document!")
                st.download_button(
                    label="Download Meeting Minutes",
                    data=docx_file,
                    file_name="meeting_minutes.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

            if "Action Items" in st.session_state.generated_minutes:
                st.subheader("Action Items")
                action_items = st.session_state.generated_minutes["Action Items"]
                st.info("Check boxes to generate documents from tasks!")
                action_items_list = action_items.split('\n')
                action_items_list = [item for item in action_items_list if item]

                action_items_dict = {}
                parent_task = None

                for item in action_items_list:
                    if item.startswith("    "):
                        if parent_task:
                            action_items_dict[parent_task].append(item.strip())
                    else:
                        parent_task = item.strip()
                        action_items_dict[parent_task] = []

                grid_data = []
                for idx, (parent, children) in enumerate(action_items_dict.items(), 1):
                    grid_data.append({
                        "Task Number": idx,
                        "Task": parent,
                        "Draft Email": False,
                        "Draft Slack": False,
                        "Draft Memo": False
                    })

                grid_df = pd.DataFrame(grid_data)

                gb = GridOptionsBuilder.from_dataframe(grid_df)
                gb.configure_column("Draft Email", editable=True, cellEditor="agCheckboxCellEditor")
                gb.configure_column("Draft Slack", editable=True, cellEditor="agCheckboxCellEditor")
                gb.configure_column("Draft Memo", editable=True, cellEditor="agCheckboxCellEditor")
                gb.configure_pagination()
                gb.configure_default_column(editable=True, resizable=True)
                grid_options = gb.build()

                grid_response = AgGrid(grid_df, gridOptions=grid_options, height=300, fit_columns on_grid_load=True, update_mode=GridUpdateMode.MODEL_CHANGED)

                if isinstance(grid_response['data'], pd.DataFrame):
                    for index, row in grid_response['data'].iterrows():
                        if row["Draft Email"]:
                            st.session_state[f"email_prompt_{row['Task Number']}"] = f"Draft an email for the following action item: {row['Task']}"
                            row["Draft Email"] = False
                        if row["Draft Slack"]:
                            st.session_state[f"slack_prompt_{row['Task Number']}"] = f"Draft a Slack message for the following action item: {row['Task']}"
                            row["Draft Slack"] = False
                        if row["Draft Memo"]:
                            st.session_state[f"memo_prompt_{row['Task Number']}"] = f"Draft a memo for the following action item: {row['Task']}"
                            row["Draft Memo"] = False

                # Add generated tasks to prompts
                for key in st.session_state.keys():
                    if key.startswith("email_prompt_"):
                        task_num = key.split('_')[-1]
                        st.subheader(f"Email Draft for Task {task_num}")
                        st.write(st.session_state[key])
                        prompt_info = {
                            "prompt": st.session_state[key],
                            "model": "gpt-4o",
                            "heading": f"Email Draft for Task {task_num}"
                        }
                        if st.button(f"Generate Email for Task {task_num}"):
                            draft = openai_client.generate_response(st.session_state.transcription, prompt_info["model"], prompt_info["prompt"])
                            st.write(draft)
                    elif key.startswith("slack_prompt_"):
                        task_num = key.split('_')[-1]
                        st.subheader(f"Slack Draft for Task {task_num}")
                        st.write(st.session_state[key])
                        prompt_info = {
                            "prompt": st.session_state[key],
                            "model": "gpt-4o",
                            "heading": f"Slack Draft for Task {task_num}"
                        }
                        if st.button(f"Generate Slack for Task {task_num}"):
                            draft = openai_client.generate_response(st.session_state.transcription, prompt_info["model"], prompt_info["prompt"])
                            st.write(draft)
                    elif key.startswith("memo_prompt_"):
                        task_num = key.split('_')[-1]
                        st.subheader(f"Memo Draft for Task {task_num}")
                        st.write(st.session_state[key])
                        prompt_info = {
                            "prompt": st.session_state[key],
                            "model": "gpt-4o",
                            "heading": f"Memo Draft for Task {task_num}"
                        }
                        if st.button(f"Generate Memo for Task {task_num}"):
                            draft = openai_client.generate_response(st.session_state.transcription, prompt_info["model"], prompt_info["prompt"])
                            st.write(draft)

if __name__ == "__main__":
    main()
