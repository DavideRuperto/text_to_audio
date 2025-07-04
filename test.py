import sys
import re
import asyncio
import pdfplumber
import edge_tts
from pathlib import Path
from pydub import AudioSegment
from shutil import copyfile

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QProgressBar, QLabel, QFileDialog
)
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont


# --- UTILITY DI TESTO ---
def normalize_text(text):
    paragraphs = text.split('\n\n')
    cleaned_paragraphs = []

    for p in paragraphs:
        p_clean = re.sub(r'\s{2,}', ' ', p)
        p_clean = re.sub(r'\n', ' ', p_clean)
        cleaned_paragraphs.append(p_clean.strip())

    return '\n\n'.join(cleaned_paragraphs)


def format_titles(text):
    text = re.sub(r'(?m)^(?P<title>[A-Z\s]{5,})$', r'<break time="700ms"/><emphasis level="strong">\g<title></emphasis><break time="500ms"/>', text)
    text = re.sub(r'(?m)^(?P<num>\d+\.\s+.*?)$', r'<break time="700ms"/><emphasis level="moderate">\g<num></emphasis><break time="400ms"/>', text)
    return text


def split_text(text, max_len=3000):
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


def read_pdf(pdf_path):
    completed_text = ''
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split('\n')

            cleaned_lines = [
                line for line in lines
                if not re.match(r'^(page\s*)?\d+(\s*/\s*\d+)?$', line.strip(), re.IGNORECASE)
            ]

            cleaned_text = '\n'.join(cleaned_lines)
            cleaned_text = re.sub(r'\[\d+\]', '', cleaned_text)

            completed_text += cleaned_text + '\n\n'
    return completed_text


# --- WORKER PER TTS ---
class TTSWorker(QThread):
    progress_updated = pyqtSignal(int)
    finished = pyqtSignal(str)

    def __init__(self, chunks, output_path, voice="it-IT-IsabellaNeural"):
        super().__init__()
        self.chunks = chunks
        self.output_path = Path(output_path)
        self.voice = voice

    async def synthesize_audio(self):
        self.output_path.mkdir(exist_ok=True)
        parts = []

        for index, chunk in enumerate(self.chunks, start=1):
            part_file = self.output_path / f"part_{index}.mp3"
            communicate = edge_tts.Communicate(text=chunk, voice=self.voice)
            await communicate.save(str(part_file))
            parts.append(part_file)

            perc = round(100 * index / len(self.chunks))
            self.progress_updated.emit(perc)

        combined = AudioSegment.empty()
        for part in parts:
            combined += AudioSegment.from_mp3(part)

        final_audio = self.output_path / "output.mp3"
        combined.export(final_audio, format="mp3")

        # Eliminazione temporanei
        for part in parts:
            if part.exists():
                part.unlink()

        self.finished.emit(str(final_audio.resolve()))

    def run(self):
        asyncio.run(self.synthesize_audio())


# --- INTERFACCIA GRAFICA ---
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sintesi vocale da PDF/TXT")
        self.setMinimumWidth(450)

        self.layout = QVBoxLayout()

        self.label = QLabel("📄 Seleziona un file PDF o TXT da sintetizzare.")
        self.progress = QProgressBar()
        self.button = QPushButton("📂 Seleziona file")
        self.save_button = QPushButton("💾 Salva file audio")
        self.save_button.setVisible(False)

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.progress)
        self.layout.addWidget(self.button)
        self.layout.addWidget(self.save_button)
        self.setLayout(self.layout)

        self.button.clicked.connect(self.load_file)
        self.save_button.clicked.connect(self.save_file_as)

        self.generated_audio_path = None
        self.original_file_stem = None

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Seleziona file", "", "Documenti (*.pdf *.txt)")
        if file_path:
            self.label.setText(f"📑 File selezionato: {Path(file_path).name}")
            self.start_tts(Path(file_path))

    def start_tts(self, file_path: Path):
        self.original_file_stem = file_path.stem

        if file_path.suffix.lower() == ".pdf":
            text = read_pdf(file_path)
            text = normalize_text(text)
            text = format_titles(text)
        elif file_path.suffix.lower() == ".txt":
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        else:
            self.label.setText("❌ Formato non supportato.")
            return

        chunks = split_text(text)
        output_path = Path(__file__).parent / 'output'
        self.worker = TTSWorker(chunks, output_path, voice="it-IT-IsabellaNeural")
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.finished.connect(self.done)
        self.worker.start()

        self.generated_audio_path = None
        self.progress.setValue(0)
        self.button.setEnabled(False)
        self.label.setText("🗣️ Sintesi in corso...")
        self.save_button.setVisible(False)

    def update_progress(self, value):
        self.progress.setValue(value)

    def done(self, output_file):
        self.generated_audio_path = output_file
        self.label.setText("✅ Sintesi completata! Pronta per il download.")
        self.button.setEnabled(True)
        self.save_button.setVisible(True)

    def save_file_as(self):
        if not self.generated_audio_path:
            return

        default_name = f"{self.original_file_stem}.mp3"
        destination, _ = QFileDialog.getSaveFileName(
            self, "Salva file audio come...", default_name, "File audio (*.mp3)"
        )

        if destination:
            copyfile(self.generated_audio_path, destination)
            # ✅ Elimina file temporaneo
            try:
                Path(self.generated_audio_path).unlink()
                self.label.setText(f"✅ File salvato in:\n{destination}\n🗑️ File temporaneo eliminato.")
            except Exception as e:
                self.label.setText(f"⚠️ Salvato, ma impossibile eliminare temporaneo:\n{e}")

            self.generated_audio_path = None
            self.save_button.setVisible(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())