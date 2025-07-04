import re
import sys
import asyncio
import pdfplumber
import edge_tts
import shutil
from pathlib import Path
from pydub import AudioSegment
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QFileDialog, QLabel

# --- ESTRAZIONE DEL TESTO DAL PDF ---
def read_file(pdf_files):
    completed_text = ''
    for file in pdf_files:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                lines = text.split('\n')

                # Rimuove numeri di pagina
                cleaned_lines = [
                    line for line in lines
                    if not re.match(r'^(page\s*)?\d+(\s*/\s*\d+)?$', line.strip(), re.IGNORECASE)
                ]

                # Rimuove note tipo [1]
                cleaned_text = '\n'.join(cleaned_lines)
                cleaned_text = re.sub(r'\[\d+\]', '', cleaned_text)

                completed_text += cleaned_text + '\n\n'

    return completed_text


# --- NORMALIZZAZIONE DEL TESTO ---
def normalize_text(text):
    # Rimuove spazi multipli all'interno delle righe, ma conserva paragrafi
    paragraphs = text.split('\n\n')
    cleaned_paragraphs = []

    for p in paragraphs:
        # pulizia interna ma senza unire tutto
        p_clean = re.sub(r'\s{2,}', ' ', p)
        p_clean = re.sub(r'\n', ' ', p_clean)  # unisce le righe interne di ogni paragrafo
        cleaned_paragraphs.append(p_clean.strip())

    return '\n\n'.join(cleaned_paragraphs)  # ripristina divisione tra paragrafi

# --- FORMATTAZIONE TITOLI E SEZIONI CON SSML ---
def format_titles(text):
    # Titoli in MAIUSCOLO
    text = re.sub(r'(?m)^(?P<title>[A-Z\s]{5,})$', r'<break time="700ms"/><emphasis level="strong">\g<title></emphasis><break time="500ms"/>', text)

    # Sezioni numerate tipo "1. Titolo"
    text = re.sub(r'(?m)^(?P<num>\d+\.\s+.*?)$', r'<break time="700ms"/><emphasis level="moderate">\g<num></emphasis><break time="400ms"/>', text)

    return text

# --- DIVISIONE DEL TESTO IN BLOCCHI ---
def split_text(text, max_len):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) < max_len:
            current += sentence + " "
        else:
            chunks.append(current.strip())
            current = sentence + " "
    if current:
        chunks.append(current.strip())

    return chunks

# --- TEXT TO SPEECH ---
async def text_to_speech_edge_tts(chunks, output_path):
    voice = "it-IT-IsabellaNeural"
    output_path.mkdir(exist_ok=True)
    parts = []

    for i, chunk in enumerate(chunks):
        part_file = output_path / f"part_{i+1}.mp3"
        print(f"🎙️ Sintesi blocco {i+1}/{len(chunks)}")
        communicate = edge_tts.Communicate(text=chunk, voice=voice)
        await communicate.save(str(part_file))
        parts.append(part_file)

    # Unione dei file mp3
    combined = AudioSegment.empty()
    for part in parts:
        combined += AudioSegment.from_mp3(part)

    final_audio = output_path / "output.mp3"
    combined.export(final_audio, format="mp3")
    print(f"\n✅ Audio finale salvato in: {final_audio.resolve()}")

# --- Classe Principale ---
class SelettorePDF(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Text to Speech") # imposta il titolo della finestra
        self.setGeometry(100, 100, 400, 150) # posizione e ridimensione della finestra (x, y, larghezza, altezza)

        self.label = QLabel("Nessun file selezionato", self) #crea un etichetta di testo per mostrare il file selezionato
        self.label.move(20, 20) # posiziona la label a 20px da sinistra e dall'alto
        self.label.resize(360, 30)

        self.button = QPushButton("Scegli file", self) # crea il bottone
        self.button.move(20, 70)
        self.button.clicked.connect(self.seleziona_pdf) # quando cliccato chiama la funzione

        self.download_button = QPushButton("Scarica .mp3", self)
        self.download_button.move(150, 70)
        self.download_button.clicked.connect(self.download_audio)
        self.download_button.setEnabled(False) #disabilitato finchè l'audio non è pronto

        self.output_dir = Path(__file__).parent / 'output'
        self.output_dir.mkdir(exist_ok=True)
        self.audio_path = self.output_dir / 'output.mp3'

    def seleziona_pdf(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona un file PDF",
            "",
            "File PDF (*.pdf)"
        )
        if file_path is not None:
            self.label.setText(f"PDF selezionato: {file_path}")
            text = read_file(file_path)
            text = normalize_text(text)
            text = format_titles(text)

            chunks = split_text(text, max_len=3000)
            
            asyncio.run(text_to_speech_edge_tts(chunks, self.output_dir))
        else:
            self.label.setText("Nessun file selezionato!")

    def download_audio(self):
        output_dir = Path(__file__).parent / 'output'

        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Salva file audio",
            "audio .mp3",
            "File audio (*.mp3)"
        )

        if destination is not None:
            try:
                shutil.copyfile(self.audio_path, destination)
                self.label.setText("Copia dell'audio salvata con successo!")
            except Exception as e:
                self.label.setText(f"Errore durante la copia: {e}")

def main():
    app = QApplication(sys.argv)
    window = SelettorePDF() #istanzia la finestra
    window.show() # mostra la finestra
    sys.exit(app.exec()) # app.exec (avvia il ciclo degli eventi (click ecc)) | sys.exit(esce con il codice di chiusura)

if __name__ == "__main__":
    main()