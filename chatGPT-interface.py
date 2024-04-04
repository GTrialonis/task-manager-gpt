import os
import traceback
import sys
import pdfplumber
import PySimpleGUI as sg
import pyperclip
from datetime import datetime
from docx import Document
import pandas as pd
from langchain.chains import ConversationalRetrievalChain
from langchain_community.chat_models import ChatOpenAI
from langchain_community.document_loaders import TextLoader
# from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import OpenAIEmbeddings  # this will be deprecated? Use the above instead?
from langchain.indexes import VectorstoreIndexCreator
from langchain.indexes.vectorstore import VectorStoreIndexWrapper
from langchain_community.vectorstores import Chroma
from constants import OPENAI_API_KEY

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
# Initialize vectorstore as None
vectorstore = None
index = None
filename = None

# Add these paths at the start of your script
ARCHIVED_TASKS_FILE = '/Users/georgiostrialonis/new-repo/Data/archived_tasks.txt'
NOTES_TAKEN_FILE = '/Users/georgiostrialonis/new-repo/Data/notes-taken.txt'

def extract_text_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ''
        for page in pdf.pages:
            text += page.extract_text() or ''
        return text


def docx_to_txt(file_path):
    # Load the .docx file with python-docx
    doc = Document(file_path)
    # Combine all the text from the document into a single string
    return '\n'.join([paragraph.text for paragraph in doc.paragraphs])


def xlsx_to_text(file_path):
    # Read the Excel file
    xls = pd.ExcelFile(file_path)

    text_content = ''
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        # Convert the DataFrame to a text string
        text_content += f"Sheet: {sheet_name}\n{df.to_string(index=False)}\n\n"

    return text_content


# Function to simulate interaction with ChatGPT
def interact_with_chatgpt(query, chat_history, index):
    # Create the chain with the selected model each time
    chain = ConversationalRetrievalChain.from_llm(
        llm=ChatOpenAI(model="gpt-4-1106-preview"),
        retriever=index.vectorstore.as_retriever(search_kwargs={"k": 1}),
    )
    result = chain({"question": query, "chat_history": chat_history})  # GPT's answer
    return result["answer"]


# Enable to save to disk & reuse the model (for repeated queries on the same data)
PERSIST = False  # Originally it was "False"
query = None

if len(sys.argv) > 1:
    query = sys.argv[1]

# Then, later in your script, when you check for persistence:
if PERSIST and os.path.exists("persist"):
    vectorstore = Chroma(
        persist_directory="persist", embedding_function=OpenAIEmbeddings()
    )
    index = VectorStoreIndexWrapper(vectorstore=vectorstore)

else:
    # Your alternative setup for vectorstore
    # For example:
    vectorstore = Chroma(embedding_function=OpenAIEmbeddings())
    index = VectorStoreIndexWrapper(vectorstore=vectorstore)
    # loader = TextLoader("data/cat.pdf")  # Use this line if you only need data.txt
    # Initialize with a default file or an empty string if you don't want to load a file at startup
    filename = "/Users/georgiostrialonis/new-repo/Data/notes-taken.txt"  # This is your default file to start with
    loader = TextLoader("/Users/georgiostrialonis/new-repo/Data/archived_tasks.txt") # choose file to interrogate
    # loader = DirectoryLoader("data/data.txt")

    # Before the event loop
loader = None
if not filename:
    pass
else:
    print('filename: ', filename)
    loader = TextLoader(filename)
    if PERSIST:
        index = VectorstoreIndexCreator(
            vectorstore_kwargs={"persist_directory": "persist"}
        ).from_loaders([loader])
    else:
        index = VectorstoreIndexCreator().from_loaders([loader])

chain = ConversationalRetrievalChain.from_llm(
    llm=ChatOpenAI(model="gpt-4-1106-preview"),
    retriever=index.vectorstore.as_retriever(search_kwargs={"k": 1}),
)

chat_history = []

# Define the theme
sg.theme('BrownBlue')

# Get current date
current_date = datetime.now().strftime("%Y-%m-%d")

# Define the layout
layout = [
    [sg.Text(current_date, key='-DATE-', pad=(5, 10), font=("Helvetica", 12))],
    [sg.Text('Select chatGPT model', font=("Helvetica", 12)),
     sg.Combo(['gpt-4-turbo-preview', 'gpt-4', 'gpt-3.5-turbo-16k'],
              key='-MODEL-', default_value='gpt-4-turbo-preview', enable_events=False),
     sg.B('Select File', key="-SELECT-"), sg.Text("No file selected", key='-FILE-')],
    [sg.Multiline(key='-OUTPUT-', size=(80, 15), autoscroll=True, disabled=True, font=("Helvetica", 16)),
     sg.Column([
         [sg.Button('Copy', font=('Helvetica', 16), size=(6, 1), key='-COPY-')],
         [sg.Button('Save', font=('Helvetica', 16), size=(6, 1), key='-SAVE-')],
         [sg.Button('Exit', font=('Helvetica', 16), size=(6, 1), key='-EXIT-')],
         [sg.Button('Clear', font=('Helvetica', 16), size=(6, 1), key='-CLEAR-', button_color=('white', 'brown'))],
     ])],
    [sg.InputText(key='-PROMPT-', size=(80, 1), do_not_clear=False, enable_events=True, font=("Helvetica", 15))],
    [sg.Button('Send', font=('Helvetica', 14), size=(5, 1), bind_return_key=True), sg.Button("Clear File Selected",
                                font=('Helvetica', 14), size=(15, 1), key='-CLEARFILE-', button_color=('White', 'Brown')),
     sg.Button('Create Encryption Key', font=('Helvetica', 14), size=(19, 1), button_color=('white', 'green'), key='-ENCRYPTION-'),
     sg.Text('Ask:', font=("Helvetica", 14)),
     sg.Button('Archived Tasks', font=('Helvetica', 14), size=(13, 1), button_color=('Black', 'LightGrey'), key='-ASK_ARCHIVED-'),
     sg.Button('Notes', font=('Helvetica', 14), size=(7, 1), button_color=('Black', 'LightGrey'), key='-ASK_NOTES-')
     ],

]

# Create the window
window = sg.Window('ChatGPT Interface', layout, return_keyboard_events=True, finalize=True)
# Bind the Enter key to an action, here we use '-ENTER-' as the event key
window.bind('<Return>', '-ENTER-')
# Force focus on the input field
window['-PROMPT-'].TKEntry.focus_force()

# This will hold the conversation history
chat_history = []

# Event loop
while True:
    event, values = window.read()

    # Set focus to the input field at the start of each loop iteration
    window['-PROMPT-'].set_focus()

    # If user closes window or clicks exit
    if event in (None, '-EXIT-', sg.WIN_CLOSED):
        break
    if event == '-CLEAR-':
        window['-OUTPUT-'].update('')

    # When the user presses the 'Send' button or the Enter key
    if event in ('Send', '-ENTER-') and values['-PROMPT-']:
        # Retrieve the selected model from the dropdown
        selected_model = values['-MODEL-']
        # Map the selection to the actual model names used by OpenAI
        model_map = {
            'gpt-4-turbo-preview': 'gpt-4-turbo-preview',
            'gpt-4': 'gpt-4',
            'gpt-3.5-turbo-16k': 'gpt-3.5-turbo-16k'
        }
        actual_model = model_map.get(selected_model, 'gpt-4-turbo-preview')

        # Get the user's input
        prompt = values['-PROMPT-']
        # Send the prompt to the ChatGPT interaction function
        response = interact_with_chatgpt(prompt, chat_history, index) # <-------------------
        # Append the response to the chat history
        chat_history.append((prompt, response))
        # Update the output Multiline with the response
        window['-OUTPUT-'].update(f'You: {prompt}\n\nChatGPT: {response}\n\n', append=True)
        # Clear the input field after sending the message
        window['-PROMPT-'].update('')
        # Force focus back to the input field
        window['-PROMPT-'].TKEntry.focus_force()

    if event == '-ASK_ARCHIVED-':
        filename = ARCHIVED_TASKS_FILE
        window['-FILE-'].update(filename)  # Just the filename for display
        loader = TextLoader(filename)  # Update your loader with the new file
        # Additional code to interact with the file...

    if event == '-ASK_NOTES-':
        filename = NOTES_TAKEN_FILE
        window['-FILE-'].update(filename)  # Just the filename for display
        loader = TextLoader(filename)  # Update your loader with the new file

    if event == '-COPY-':
        responses = values['-OUTPUT-']
        pyperclip.copy(responses)

    # Save chat responses to a file
    if event == '-SAVE-':
        responses = values['-OUTPUT-']
        with open('/Users/georgiostrialonis/new-repo/chat_history.txt', 'a') as file:
            file.write(responses)
        sg.popup('Responses saved!', keep_on_top=True)

    # File selection
    if event == '-SELECT-':
        chosen_file = sg.popup_get_file('Select a file', no_window=True, file_types=(
        ("All Files", "*.*"), ("Text Files", "*.txt"), ("Exel Documents", "*.xlsx"), ("Word Documents", "*.docx"),
        ("PDF Files", "*.pdf")))
        if chosen_file:
            filename = chosen_file
            window['-FILE-'].update(filename)

            if filename.lower().endswith('.docx'):
                try:
                    text_content = docx_to_txt(filename)
                    # system expects a file path
                    temp_filename = '/Users/georgiostrialonis/new-repo/temp_extracted_text.txt'
                    with open(temp_filename, 'w', encoding='utf-8') as temp_file:
                        temp_file.write(text_content)
                    # Now update your loader to use the temporary file
                    loader = TextLoader(temp_filename)
                except Exception as e:
                    sg.popup_error(f'Failed to process Word document: {e}')
# ---------------------------------------------------------------------
#             elif filename.lower().endswith('.pdf'):
#
#                 try:
#                     text_content = extract_text_from_pdf(filename)
#                     temp_filename = '/Users/georgiostrialonis/new-repo/temp_extracted_text.txt'
#                     with open(temp_filename, 'w', encoding='utf-8') as temp_file:
#                         temp_file.write(text_content)
#                     loader = TextLoader(temp_filename)
#                 except Exception as e:
#                     print(f'Failed to process PDF document: {e}')
#                     traceback.print_exc()  # Print the full traceback
# -----------------------------------------------------------------------------
#             # Process the .txt file
#             elif filename.lower().endswith('.txt'):
#                 try:
#                     # For .txt files, directly use the TextLoader with the file path
#                     loader = TextLoader(filename)
#                 except Exception as e:
#                     sg.popup_error(f'Failed to process text file: {e}')
# ---------------------------------------------------------------------------------
            # Process the .xlsx file
            elif filename.lower().endswith('.xlsx'):
                try:
                    text_content = xlsx_to_text(filename)
                    temp_filename = '/Users/georgiostrialonis/new-repo/temp_extracted_text.txt'
                    with open(temp_filename, 'w', encoding='utf-8') as temp_file:
                        temp_file.write(text_content)
                    loader = TextLoader(temp_filename)
                except Exception as e:
                    sg.popup_error(f'Failed to process Excel document: {e}')
            else:
                sg.popup_error(f'Unsupported file type selected.')
# --------------------------- να το αφαιρέσω; -----------------------------------
        else:
            # Your existing processing for .txt and .pdf files
            loader = TextLoader(filename)
# -------------------------------------------------------------
        # Re-create the index with the new loader
        if PERSIST:
            index = VectorstoreIndexCreator(
                vectorstore_kwargs={"persist_directory": "persist"}
            ).from_loaders([loader])
        else:
            index = VectorstoreIndexCreator().from_loaders([loader])
        # Update the chain if necessary
        chain = ConversationalRetrievalChain.from_llm(
            llm=ChatOpenAI(model="gpt-4-turbo-preview"),
            retriever=index.vectorstore.as_retriever(search_kwargs={"k": 1}),
        )
    # CLEAR file name
    if event == '-CLEARFILE-':
        filename = None  # this re-sets the filename variable
        window['-FILE-'].update('No file selected')

# Finish up by removing from the screen
window.close()