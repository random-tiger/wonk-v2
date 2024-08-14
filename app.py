import streamlit as st
from io import BytesIO
from file_handlers import process_files_concurrently, save_as_docx
from openai_client import OpenAIClient
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_quill import st_quill
import pandas as pd

# Initialize OpenAI client
try:
    openai_client = OpenAIClient()
except ValueError as e:
    st.error(f"Error initializing OpenAI client: {e}")
    st.stop()

def main():
    st.sidebar.title("Wonk")
    st.sidebar.info("Upload mp3, mp4, mov, docx, txt, xlsx, pdf, pptx, or image files to start!")
    uploaded_files = st.sidebar.file_uploader("Upload files", type=["mp3", "mp4", "mov", "docx", "txt", "xlsx", "pdf", "pptx", "jpg", "jpeg", "png"], accept_multiple_files=True)
    process_files_button = st.sidebar.button("Process Files")

    if uploaded_files and process_files_button:
        if "transcriptions" not in st.session_state:
            st.session_state.transcriptions = []

        transcriptions = process_files_concurrently(uploaded_files, openai_client)
        st.session_state.transcriptions.extend(transcriptions)

        if st.session_state.transcriptions:
            combined_transcription = "\n\n".join(st.session_state.transcriptions)
            st.session_state.transcription = combined_transcription

    transcription = st.session_state.get("transcription", "")
    editor_content = st.session_state.get("editor_content", "")

    if transcription:
        with st.expander("Transcription", expanded=True):
            st.subheader("Transcription")
            editor_content = st_quill(value=transcription, key='transcription_editor')

            if editor_content != st.session_state.get("editor_content"):
                st.session_state.editor_content = editor_content

        st.sidebar.info("Select what you'd like to create!")
        summary_type = st.sidebar.radio(
            "Select the type of summary you want to generate:",
            ("", "Meeting Summary", "User Research Synthesis", "Action Items", "Retro", "Document Review"),
            index=0
        )

        if 'prompts' not in st.session_state:
            st.session_state.prompts = []

        checkboxes = {}
        # Define checkbox options based on summary_type
        if summary_type == "Meeting Summary":
            st.sidebar.markdown("### Meeting Summary Prompts")
            checkboxes = {
                "summary": st.sidebar.checkbox("Summary"),
                "key_points": st.sidebar.checkbox("Key Points"),
                "action_items": st.sidebar.checkbox("Action Items"),
                "sentiment": st.sidebar.checkbox("Sentiment Analysis")
            }
        elif summary_type == "User Research Synthesis":
            st.sidebar.markdown("### User Research Synthesis Prompts")
            checkboxes = {
                "summary": st.sidebar.checkbox("Summary", key="user_summary"),
                "biographical_info": st.sidebar.checkbox("Biographical Info"),
                "key_insights": st.sidebar.checkbox("Key Insights"),
                "recommendations": st.sidebar.checkbox("Recommendations")
            }
        elif summary_type == "Action Items":
            st.sidebar.markdown("### Action Items Prompt")
            checkboxes = {"action_items": st.sidebar.checkbox("Action Items", key="action_items")}
        elif summary_type == "Retro":
            st.sidebar.markdown("### Retro Prompts")
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

if __name__ == "__main__":
    main()
